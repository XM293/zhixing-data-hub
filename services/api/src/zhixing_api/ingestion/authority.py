from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import exists, select
from sqlalchemy.sql.elements import ColumnElement
from zhixing_connectors.catalog import RESOURCE_CATALOG, can_project_to_core, resource_spec

from zhixing_api.actor_context import ActorContext, actor_scope_allows, require_permission
from zhixing_api.data_models import (
    BusinessUnit,
    CanonicalAfterSale,
    CanonicalFulfillment,
    CanonicalInventoryBalance,
    CanonicalSalesOrder,
    ExternalSystem,
    PlatformEvent,
    SourceAuthorityAssignment,
    SourceResource,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem
from zhixing_api.governance_service import _governable_enterprises
from zhixing_api.scope_context import build_scope_context

FactFamily = Literal["orders", "after_sales", "inventory", "fulfillments"]
FactModel = (type[CanonicalSalesOrder] | type[CanonicalAfterSale]
             | type[CanonicalInventoryBalance] | type[CanonicalFulfillment])


class AuthorityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    business_unit_id: str = Field(min_length=1, max_length=64)
    source_key: str = Field(min_length=1, max_length=80)
    fact_family: FactFamily
    resource_key: str = Field(min_length=1, max_length=120)
    status: Literal["active", "disabled"] = "active"
    expected_version: int = Field(default=0, ge=0)


class AuthorityView(BaseModel):
    schema_version: int = 2
    id: str
    enterprise_id: str
    business_unit_id: str
    source_key: str
    fact_family: str
    resource_key: str
    status: str
    version: int
    updated_at: datetime


def _view(row: SourceAuthorityAssignment, source: ExternalSystem) -> AuthorityView:
    return AuthorityView(id=row.id, enterprise_id=row.enterprise_id,
        business_unit_id=row.business_unit_id, source_key=source.system_key,
        fact_family=row.fact_family, resource_key=row.resource_key, status=row.status,
        version=row.version, updated_at=row.updated_at)


def list_authorities(database: Database, actor: ActorContext) -> list[AuthorityView]:
    require_permission(actor, "source.manage", database,
                       resource_type="source-authority", resource_key="list")
    scope = build_scope_context(database, actor)
    with database.session() as session:
        rows = session.execute(select(SourceAuthorityAssignment, ExternalSystem)
            .join(ExternalSystem, ExternalSystem.id == SourceAuthorityAssignment.external_system_id)
            .where(SourceAuthorityAssignment.enterprise_id == actor.enterprise_id,
                   SourceAuthorityAssignment.business_unit_id.in_(scope.business_unit_ids))
            .order_by(SourceAuthorityAssignment.business_unit_id,
                      SourceAuthorityAssignment.fact_family))
        return [_view(rule, source) for rule, source in rows]


def save_authority(database: Database, actor: ActorContext,
                    payload: AuthorityRequest) -> AuthorityView:
    require_permission(actor, "source.manage", database,
                       resource_type="source-authority", resource_key=payload.business_unit_id)
    scope = build_scope_context(database, actor)
    can_manage = (actor.enterprise_id in _governable_enterprises(database, actor)
                  or actor_scope_allows(actor, scope_type="business_unit",
                                        scope_id=payload.business_unit_id, database=database))
    if payload.business_unit_id not in scope.business_unit_ids or not can_manage:
        raise ApiProblem(status_code=403, code="authority.scope_denied", message="业务单元未获授权")
    spec = resource_spec(payload.resource_key)
    if spec is None or not can_project_to_core(spec) or spec.mapping_key != payload.fact_family:
        raise ApiProblem(status_code=422, code="authority.resource_invalid",
                         message="资源不具备对应事实族的已确认映射")
    with database.session() as session:
        unit = session.get(BusinessUnit, payload.business_unit_id, with_for_update=True)
        source = session.scalar(select(ExternalSystem).where(
            ExternalSystem.enterprise_id == actor.enterprise_id,
            ExternalSystem.system_key == payload.source_key))
        if (unit is None or unit.enterprise_id != actor.enterprise_id or unit.status != "active"
                or source is None or source.business_unit_id not in {None, unit.id}):
            raise ApiProblem(status_code=422, code="authority.source_scope_invalid",
                             message="来源与业务单元归属不一致")
        resource = session.scalar(select(SourceResource).where(
            SourceResource.external_system_id == source.id,
            SourceResource.resource_key == payload.resource_key))
        if payload.status == "active" and (source.status == "disabled" or resource is None
                or not resource.enabled or resource.schema_status != "confirmed"):
            raise ApiProblem(status_code=409, code="authority.resource_unavailable",
                             message="来源或资源未启用或 Schema 未确认")
        row = session.scalar(select(SourceAuthorityAssignment).where(
            SourceAuthorityAssignment.enterprise_id == actor.enterprise_id,
            SourceAuthorityAssignment.business_unit_id == unit.id,
            SourceAuthorityAssignment.fact_family == payload.fact_family).with_for_update())
        if payload.expected_version != (row.version if row else 0):
            raise ApiProblem(status_code=409, code="authority.version_conflict",
                             message="权威规则已更新，请刷新后重试")
        now = datetime.now(UTC)
        if row is None:
            row = SourceAuthorityAssignment(id=f"authority_{uuid4().hex}",
                enterprise_id=actor.enterprise_id, business_unit_id=unit.id,
                fact_family=payload.fact_family, version=0, created_at=now)
            session.add(row)
        row.external_system_id, row.resource_key = source.id, payload.resource_key
        row.status, row.updated_at, row.version = payload.status, now, row.version + 1
        session.add(PlatformEvent(id=f"event_{uuid4().hex}", enterprise_id=actor.enterprise_id,
            event_type="source.authority_saved", severity="info", title="权威来源变更",
            detail=f"assignment_id={row.id}; source_id={source.id}; version={row.version}; "
                   f"principal_id={actor.principal_id}; status={row.status}", occurred_at=now))
        session.commit()
        return _view(row, source)


def authority_condition(model: FactModel, family: FactFamily) -> ColumnElement[bool]:
    rule = SourceAuthorityAssignment
    confirmed_resources = [item.key for item in RESOURCE_CATALOG
                           if can_project_to_core(item) and item.mapping_key == family]
    return exists(select(rule.id).join(ExternalSystem,
        ExternalSystem.id == rule.external_system_id).join(BusinessUnit,
        BusinessUnit.id == rule.business_unit_id).join(SourceResource,
        (SourceResource.external_system_id == rule.external_system_id)
        & (SourceResource.resource_key == rule.resource_key)).where(
            rule.enterprise_id == model.enterprise_id,
            rule.business_unit_id == model.business_unit_id,
            rule.external_system_id == model.external_system_id,
            rule.resource_key == model.resource_key, rule.fact_family == family,
            rule.resource_key.in_(confirmed_resources),
            rule.status == "active", ExternalSystem.status != "disabled",
            ExternalSystem.enterprise_id == rule.enterprise_id,
            BusinessUnit.enterprise_id == rule.enterprise_id, BusinessUnit.status == "active",
            SourceResource.enabled.is_(True), SourceResource.schema_status == "confirmed"))
