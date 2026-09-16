"""Authorized organization and source-location projection; no synthetic scene state."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from zhixing_connectors.catalog import effective_schema_status, resource_spec

from zhixing_api.data_models import (
    BusinessEntity,
    BusinessUnit,
    CanonicalEntityOrigin,
    Enterprise,
    EnterpriseGroup,
    ExternalSystem,
    SourceResource,
)
from zhixing_api.database import Database
from zhixing_api.scope_context import ScopeContext


class OrganizationNode(BaseModel):
    id: str
    parent_id: str | None
    kind: Literal["group", "enterprise", "business_unit"]
    name: str


class SourceLocation(BaseModel):
    origin_id: str
    entity_id: str
    enterprise_id: str
    business_unit_id: str
    kind: Literal["store", "warehouse"]
    name: str
    entity_status: str
    source_id: str
    source_name: str
    source_status: str
    connection_status: str
    resource_key: str
    resource_enabled: bool
    schema_status: str
    observed_at: datetime


class ScopeTwinProjection(BaseModel):
    schema_version: Literal[1] = 1
    scope_snapshot: dict[str, object]
    organizations: list[OrganizationNode]
    locations: list[SourceLocation]
    total: int
    offset: int
    limit: int
    data_as_of: datetime | None


def project_scope_twin(database: Database, scope: ScopeContext, *,
                       offset: int = 0, limit: int = 100) -> ScopeTwinProjection:
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("scope_twin.page_invalid")
    legal_ids = set(scope.selected_enterprise_ids) & set(scope.allowed_enterprise_ids)
    with database.session() as session:
        legal_rows = session.scalars(select(Enterprise).where(
            Enterprise.id.in_(legal_ids), Enterprise.group_id == scope.group_id)
            .order_by(Enterprise.name, Enterprise.id)).all()
        legal_ids = {row.id for row in legal_rows}
        units = session.scalars(select(BusinessUnit).where(
            BusinessUnit.enterprise_id.in_(legal_ids), BusinessUnit.id.in_(scope.business_unit_ids),
            BusinessUnit.status == "active").order_by(BusinessUnit.name, BusinessUnit.id)).all()
        unit_ids = {row.id for row in units}
        origin, entity, source, resource = (CanonicalEntityOrigin, BusinessEntity,
                                             ExternalSystem, SourceResource)
        store_keys = () if scope.scope_level == "warehouse" else scope.store_ids
        warehouse_keys = () if scope.scope_level == "store" else scope.warehouse_ids
        statement = select(origin, entity, source, resource).select_from(origin).join(
            entity, and_(entity.id == origin.entity_id,
                         entity.enterprise_id == origin.enterprise_id)).join(
            source, and_(source.id == origin.external_system_id,
                         source.enterprise_id == origin.enterprise_id)).join(
            BusinessUnit, and_(BusinessUnit.id == origin.business_unit_id,
                               BusinessUnit.enterprise_id == origin.enterprise_id)).outerjoin(
            resource, and_(resource.external_system_id == source.id,
                           resource.resource_key == origin.resource_key)).where(
                origin.enterprise_id.in_(legal_ids), origin.business_unit_id.in_(unit_ids),
                origin.status == "assigned", or_(
                    and_(entity.entity_type == "store", entity.canonical_key.in_(store_keys)),
                    and_(entity.entity_type == "warehouse",
                         entity.canonical_key.in_(warehouse_keys))))
        if scope.scope_level in {"store", "warehouse"}:
            location_units = set(session.scalars(
                statement.with_only_columns(origin.business_unit_id).distinct()))
            units = [unit for unit in units if unit.id in location_units]
            unit_ids = {unit.id for unit in units}
        if scope.scope_level not in {"group", "enterprise"}:
            unit_legal_ids = {unit.enterprise_id for unit in units}
            legal_rows = [row for row in legal_rows if row.id in unit_legal_ids]
        group = (session.get(EnterpriseGroup, scope.group_id)
                 if scope.group_id and legal_rows else None)
        nodes = ([OrganizationNode(id=group.id, parent_id=None, kind="group", name=group.name)]
                 if group else [])
        nodes += [OrganizationNode(id=row.id, parent_id=group.id if group else None,
                                   kind="enterprise", name=row.name) for row in legal_rows]
        nodes += [OrganizationNode(id=row.id,
            parent_id=row.parent_id if row.parent_id in unit_ids else row.enterprise_id,
            kind="business_unit", name=row.name) for row in units]
        matching = statement.with_only_columns(origin.observed_at).subquery()
        total, latest = session.execute(select(func.count(),
            func.max(matching.c.observed_at)).select_from(matching)).one()
        rows = session.execute(statement.order_by(origin.enterprise_id, origin.business_unit_id,
            entity.display_name, origin.id).offset(offset).limit(limit)).all()
        locations = [SourceLocation(origin_id=o.id, entity_id=e.id, enterprise_id=o.enterprise_id,
            business_unit_id=o.business_unit_id, kind=e.entity_type, name=e.display_name,
            entity_status=e.status, source_id=s.id, source_name=s.name, source_status=s.status,
            connection_status=s.connection_status, resource_key=o.resource_key,
            resource_enabled=bool(r and r.enabled),
            schema_status=effective_schema_status(resource_spec(o.resource_key),
                r.schema_status if r else "schema_pending"), observed_at=o.observed_at)
            for o, e, s, r in rows]
        snapshot = scope.snapshot()
        snapshot["data_as_of"] = latest.isoformat() if latest else None
        return ScopeTwinProjection(scope_snapshot=snapshot, organizations=nodes,
            locations=locations, total=total, offset=offset, limit=limit, data_as_of=latest)
