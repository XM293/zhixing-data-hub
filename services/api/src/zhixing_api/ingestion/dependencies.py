"""Extract bounded source values for dependent read-only resource fanout."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import Connection, Table, and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from zhixing_connectors.catalog import resource_spec

from zhixing_api.data_models import (
    ExternalSystem,
    SourceDependencyTuple,
    SourceDependencyValue,
    SourceResource,
)

EXTRACTOR_VERSION = "4"

# Exact provider field names only. A new alias must be backed by an official response contract.
DEPENDENCY_FIELDS: dict[str, str] = {
    "amazonOrderId": "amazonOrderId",
    "asin": "asin",
    "categoryUniqueId": "categoryUniqueId",
    "currencyCode": "currencyCode",
    "financialEventGroupId": "financialEventGroupId",
    "inboundPlanId": "inboundPlanId",
    "invoice_id": "invoice_id",
    "marketplaceId": "marketplaceId",
    "msku": "msku",
    "orderId": "orderId",
    "parentAsin": "parentAsin",
    "report_document_id": "report_document_id",
    "seller_id": "seller_id",
    "sellerSku": "sellerSku",
    "shipmentId": "shipmentId",
    "shipment_id": "shipment_id",
    "spu": "spu",
}
STORE_SCOPE_FIELDS = ("sid", "store_id", "storeId")


@dataclass(frozen=True, slots=True)
class DependencyPersistResult:
    discovered: int
    created: int
    updated: int
    tuples_discovered: int = 0
    tuples_created: int = 0
    tuples_updated: int = 0


class DependencyValueView(BaseModel):
    id: str
    source_resource_id: str
    resource_key: str
    business_unit_id: str | None
    value_type: str
    external_value: str
    scope_kind: str
    scope_external_key: str
    status: str
    first_manifest_id: str
    last_manifest_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
    extractor_version: str


class DependencyValueList(BaseModel):
    items: list[DependencyValueView]
    total: int
    offset: int
    limit: int


@dataclass(frozen=True, slots=True)
class _Candidate:
    value_type: str
    external_value: str
    value_hash: str
    scope_kind: str
    scope_external_key: str


@dataclass(frozen=True, slots=True)
class _TupleCandidate:
    tuple_type: str
    tuple_values: dict[str, str]
    tuple_hash: str
    scope_kind: str
    scope_external_key: str


def _scalar_text(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip()
    return text if text and len(text) <= 300 else None


def _store_scope(value: object, namespace: str) -> tuple[str, str] | None:
    text = _scalar_text(value)
    prefix = "store:multiplatform:" if namespace == "multiplatform" else "store:"
    return ("store", f"{prefix}{text}") if text is not None else None


def _request_store_scope(parameters: dict[str, object], namespace: str) -> tuple[str, str] | None:
    candidates: set[str] = set()

    def visit(value: object, key: str | None = None) -> None:
        if key in STORE_SCOPE_FIELDS:
            if isinstance(value, list):
                candidates.update(text for item in value if (text := _scalar_text(item)))
            elif (text := _scalar_text(value)) is not None:
                candidates.add(text)
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, child_key)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(parameters)
    value = next(iter(candidates)) if len(candidates) == 1 else None
    prefix = "store:multiplatform:" if namespace == "multiplatform" else "store:"
    return ("store", f"{prefix}{value}") if value is not None else None


def _extract(payload: dict[str, Any], request_parameters: dict[str, object],
             namespace: str) -> list[_Candidate]:
    fallback_scope = _request_store_scope(request_parameters, namespace) or ("source", "")
    found: dict[tuple[str, str, str, str], _Candidate] = {}

    def visit(value: object, inherited_scope: tuple[str, str]) -> None:
        if isinstance(value, dict):
            local_scope = inherited_scope
            for scope_field in STORE_SCOPE_FIELDS:
                if scope_field in value and (
                    scope := _store_scope(value[scope_field], namespace)
                ) is not None:
                    local_scope = scope
                    break
            for field, child in value.items():
                value_type = DEPENDENCY_FIELDS.get(field)
                text = _scalar_text(child) if value_type is not None else None
                if value_type is not None and text is not None:
                    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    identity = (value_type, digest, local_scope[0], local_scope[1])
                    found[identity] = _Candidate(
                        value_type, text, digest, local_scope[0], local_scope[1])
                if isinstance(child, (dict, list)):
                    visit(child, local_scope)
        elif isinstance(value, list):
            for child in value:
                visit(child, inherited_scope)

    visit(payload, fallback_scope)
    return [found[key] for key in sorted(found)]


def _extract_tuples(
    payload: dict[str, Any], request_parameters: dict[str, object], namespace: str,
) -> list[_TupleCandidate]:
    """Extract only reviewed same-object relationships; never build a Cartesian product."""
    fallback_scope = _request_store_scope(request_parameters, namespace) or ("source", "")
    found: dict[tuple[str, str, str, str], _TupleCandidate] = {}

    def visit(value: object, inherited_scope: tuple[str, str]) -> None:
        if isinstance(value, dict):
            local_scope = inherited_scope
            for scope_field in STORE_SCOPE_FIELDS:
                if scope_field in value and (
                    scope := _store_scope(value[scope_field], namespace)
                ) is not None:
                    local_scope = scope
                    break
            inbound_plan_id = _scalar_text(value.get("inboundPlanId"))
            shipment_id = (_scalar_text(value.get("shipmentId"))
                           or _scalar_text(value.get("shipment_id")))
            if inbound_plan_id is not None and shipment_id is not None:
                tuple_type = "inboundPlanId+shipmentId"
                tuple_values = {
                    "inboundPlanId": inbound_plan_id,
                    "shipmentId": shipment_id,
                }
                encoded = json.dumps(
                    tuple_values, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
                identity = (tuple_type, digest, local_scope[0], local_scope[1])
                found[identity] = _TupleCandidate(
                    tuple_type, tuple_values, digest, local_scope[0], local_scope[1]
                )
            for child in value.values():
                if isinstance(child, (dict, list)):
                    visit(child, local_scope)
        elif isinstance(value, list):
            for child in value:
                visit(child, inherited_scope)

    visit(payload, fallback_scope)
    return [found[key] for key in sorted(found)]


def persist_dependency_values(
    connection: Connection,
    *,
    enterprise_id: str,
    external_system_id: str,
    source_resource_id: str,
    resource_key: str,
    manifest_id: str,
    payload: dict[str, Any],
    request_parameters: dict[str, object],
    observed_at: datetime,
) -> DependencyPersistResult:
    """Upsert extracted values inside the Raw manifest/checkpoint transaction."""
    source = connection.execute(select(
        ExternalSystem.enterprise_id, ExternalSystem.business_unit_id,
        SourceResource.resource_key,
    ).join(SourceResource, SourceResource.external_system_id == ExternalSystem.id).where(
        ExternalSystem.id == external_system_id,
        SourceResource.id == source_resource_id,
    )).one_or_none()
    if (source is None or source.enterprise_id != enterprise_id
            or source.resource_key != resource_key):
        raise ValueError("source.dependency_scope_changed")
    spec = resource_spec(resource_key)
    namespace = (spec.scope_namespace if spec is not None and spec.scope_namespace else "amazon")
    candidates = _extract(payload, request_parameters, namespace)
    tuples = _extract_tuples(payload, request_parameters, namespace)
    if not candidates and not tuples:
        return DependencyPersistResult(discovered=0, created=0, updated=0)
    observed_at = (observed_at.replace(tzinfo=UTC) if observed_at.tzinfo is None
                   else observed_at.astimezone(UTC))
    table = cast(Table, SourceDependencyValue.__table__)
    identities = [and_(
        table.c.external_system_id == external_system_id,
        table.c.value_type == item.value_type,
        table.c.value_hash == item.value_hash,
        table.c.scope_kind == item.scope_kind,
        table.c.scope_external_key == item.scope_external_key,
    ) for item in candidates]
    existing = set(connection.execute(select(
        table.c.value_type, table.c.value_hash, table.c.scope_kind,
        table.c.scope_external_key).where(*([] if not identities else [identities[0]])
    )).all()) if len(identities) == 1 else set()
    if len(identities) > 1:
        existing = set(connection.execute(select(
            table.c.value_type, table.c.value_hash, table.c.scope_kind,
            table.c.scope_external_key).where(or_(*identities))).all())
    created = 0
    for item in candidates:
        identity = (item.value_type, item.value_hash, item.scope_kind, item.scope_external_key)
        values = {
            "id": f"dependency_{uuid4().hex}",
            "enterprise_id": enterprise_id,
            "external_system_id": external_system_id,
            "source_resource_id": source_resource_id,
            "first_manifest_id": manifest_id,
            "last_manifest_id": manifest_id,
            "business_unit_id": source.business_unit_id,
            "value_type": item.value_type,
            "external_value": item.external_value,
            "value_hash": item.value_hash,
            "scope_kind": item.scope_kind,
            "scope_external_key": item.scope_external_key,
            "status": "active",
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "occurrence_count": 1,
            "extractor_version": EXTRACTOR_VERSION,
        }
        insert = (postgresql_insert(table) if connection.dialect.name == "postgresql"
                  else sqlite_insert(table)).values(**values)
        excluded = insert.excluded
        statement = insert.on_conflict_do_update(
            index_elements=["external_system_id", "value_type", "value_hash", "scope_kind",
                            "scope_external_key"],
            set_={
                "source_resource_id": excluded.source_resource_id,
                "last_manifest_id": case(
                    (excluded.last_seen_at >= table.c.last_seen_at,
                     excluded.last_manifest_id),
                    else_=table.c.last_manifest_id),
                "business_unit_id": excluded.business_unit_id,
                "external_value": excluded.external_value,
                "status": "active",
                "last_seen_at": case(
                    (excluded.last_seen_at >= table.c.last_seen_at, excluded.last_seen_at),
                    else_=table.c.last_seen_at),
                "occurrence_count": table.c.occurrence_count + 1,
                "extractor_version": EXTRACTOR_VERSION,
            })
        connection.execute(statement)
        created += identity not in existing
    tuple_table = cast(Table, SourceDependencyTuple.__table__)
    tuple_identities = [and_(
        tuple_table.c.external_system_id == external_system_id,
        tuple_table.c.tuple_type == item.tuple_type,
        tuple_table.c.tuple_hash == item.tuple_hash,
        tuple_table.c.scope_kind == item.scope_kind,
        tuple_table.c.scope_external_key == item.scope_external_key,
    ) for item in tuples]
    existing_tuples: set[tuple[str, str, str, str]] = set()
    if tuple_identities:
        existing_tuples = {tuple(row) for row in connection.execute(select(
            tuple_table.c.tuple_type, tuple_table.c.tuple_hash,
            tuple_table.c.scope_kind, tuple_table.c.scope_external_key,
        ).where(or_(*tuple_identities))).all()}
    tuples_created = 0
    for tuple_item in tuples:
        identity = (tuple_item.tuple_type, tuple_item.tuple_hash, tuple_item.scope_kind,
                    tuple_item.scope_external_key)
        values = {
            "id": f"dependency_tuple_{uuid4().hex}",
            "enterprise_id": enterprise_id,
            "external_system_id": external_system_id,
            "source_resource_id": source_resource_id,
            "first_manifest_id": manifest_id,
            "last_manifest_id": manifest_id,
            "business_unit_id": source.business_unit_id,
            "tuple_type": tuple_item.tuple_type,
            "tuple_values": tuple_item.tuple_values,
            "tuple_hash": tuple_item.tuple_hash,
            "scope_kind": tuple_item.scope_kind,
            "scope_external_key": tuple_item.scope_external_key,
            "status": "active",
            "first_seen_at": observed_at,
            "last_seen_at": observed_at,
            "occurrence_count": 1,
            "extractor_version": EXTRACTOR_VERSION,
        }
        insert = (postgresql_insert(tuple_table)
                  if connection.dialect.name == "postgresql"
                  else sqlite_insert(tuple_table)).values(**values)
        excluded = insert.excluded
        statement = insert.on_conflict_do_update(
            index_elements=["external_system_id", "tuple_type", "tuple_hash", "scope_kind",
                            "scope_external_key"],
            set_={
                "source_resource_id": excluded.source_resource_id,
                "last_manifest_id": case(
                    (excluded.last_seen_at >= tuple_table.c.last_seen_at,
                     excluded.last_manifest_id),
                    else_=tuple_table.c.last_manifest_id),
                "business_unit_id": excluded.business_unit_id,
                "tuple_values": excluded.tuple_values,
                "status": "active",
                "last_seen_at": case(
                    (excluded.last_seen_at >= tuple_table.c.last_seen_at,
                     excluded.last_seen_at),
                    else_=tuple_table.c.last_seen_at),
                "occurrence_count": tuple_table.c.occurrence_count + 1,
                "extractor_version": EXTRACTOR_VERSION,
            },
        )
        connection.execute(statement)
        tuples_created += identity not in existing_tuples
    return DependencyPersistResult(
        discovered=len(candidates), created=created, updated=len(candidates) - created,
        tuples_discovered=len(tuples), tuples_created=tuples_created,
        tuples_updated=len(tuples) - tuples_created,
    )


def list_dependency_values(
    session: Session,
    *,
    enterprise_id: str,
    external_system_id: str,
    offset: int,
    limit: int,
    value_type: str | None = None,
    status: str | None = None,
    scope_kind: str | None = None,
    resource_key: str | None = None,
) -> DependencyValueList:
    predicates = [
        SourceDependencyValue.enterprise_id == enterprise_id,
        SourceDependencyValue.external_system_id == external_system_id,
        ExternalSystem.id == external_system_id,
        ExternalSystem.enterprise_id == enterprise_id,
    ]
    if value_type is not None:
        predicates.append(SourceDependencyValue.value_type == value_type)
    if status is not None:
        predicates.append(SourceDependencyValue.status == status)
    if scope_kind is not None:
        predicates.append(SourceDependencyValue.scope_kind == scope_kind)
    if resource_key is not None:
        predicates.append(SourceResource.resource_key == resource_key)
    base = select(SourceDependencyValue, SourceResource.resource_key).join(
        SourceResource, SourceResource.id == SourceDependencyValue.source_resource_id,
    ).join(
        ExternalSystem, ExternalSystem.id == SourceDependencyValue.external_system_id,
    ).where(*predicates)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.execute(base.order_by(
        SourceDependencyValue.last_seen_at.desc(), SourceDependencyValue.id,
    ).offset(offset).limit(limit)).all()
    return DependencyValueList(
        items=[DependencyValueView(
            id=row.id, source_resource_id=row.source_resource_id,
            resource_key=resolved_resource_key, business_unit_id=row.business_unit_id,
            value_type=row.value_type, external_value=row.external_value,
            scope_kind=row.scope_kind, scope_external_key=row.scope_external_key,
            status=row.status, first_manifest_id=row.first_manifest_id,
            last_manifest_id=row.last_manifest_id, first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at, occurrence_count=row.occurrence_count,
            extractor_version=row.extractor_version,
        ) for row, resolved_resource_key in rows],
        total=total, offset=offset, limit=limit,
    )
