from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection, delete, select
from sqlalchemy.orm import Session
from zhixing_connectors.catalog import resource_spec, response_value

from zhixing_api.data_models import (
    BusinessEntity,
    BusinessUnit,
    CanonicalAfterSale,
    CanonicalEntityOrigin,
    CanonicalFulfillment,
    CanonicalFulfillmentLine,
    CanonicalInventoryBalance,
    CanonicalOperationalFact,
    CanonicalSalesOrder,
    CanonicalSalesOrderLine,
    ExternalSystem,
    MappingConflict,
    RawPageManifest,
    SourceBinding,
    StagingPageResult,
)

from .after_sales import map_after_sales
from .conflicts import mark_resolved
from .fulfillments import map_fulfillment
from .mapping import (
    MAPPING_VERSION,
    SCHEMA_VERSION,
    EntityInput,
    map_brand,
    map_category,
    map_concept_shop,
    map_head_logistics_provider,
    map_listing,
    map_logistics_channel,
    map_marketplace,
    map_multiplatform_shop,
    map_order,
    map_product,
    map_product_tag,
    map_shop,
    map_source_user,
    map_spu,
    map_stock,
    map_subdivision,
    map_supplier,
    map_warehouse,
)
from .operational_facts import (
    OperationalFactInput,
    map_ad_campaign,
    map_customer_review,
    map_exchange_rate,
    map_fba_inventory,
    map_fba_shipment,
    map_fbm_order,
    map_finance_fee,
    map_inventory_document,
    map_inventory_statement,
    map_product_attribute,
    map_purchase_order,
    map_source_order,
    map_warehouse_bin,
)


@dataclass
class PageCounts:
    accepted: int = 0
    rejected: int = 0
    unassigned: int = 0
    stale: int = 0


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def stable_key(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def _binding(session: Session, source: ExternalSystem, kind: str, key: str) -> SourceBinding:
    binding = _approved_binding(session, source, kind, key)
    if binding is None:
        raise LookupError("mapping.unassigned")
    return binding


def _approved_binding(
    session: Session, source: ExternalSystem, kind: str, key: str,
) -> SourceBinding | None:
    return session.scalar(select(SourceBinding).join(
        BusinessUnit, BusinessUnit.id == SourceBinding.business_unit_id
    ).where(
        SourceBinding.enterprise_id == source.enterprise_id,
        SourceBinding.source_system_id == source.id,
        SourceBinding.canonical_type == kind,
        SourceBinding.external_key == f"{kind}:{key}",
        SourceBinding.status == "approved",
        BusinessUnit.enterprise_id == source.enterprise_id,
        BusinessUnit.status == "active",
    ).with_for_update(of=SourceBinding))


def _suggest_binding(
    session: Session, source: ExternalSystem, *, kind: str, external_key: str,
    anchors: dict[str, SourceBinding], resource: str, manifest: str,
    observed_at: datetime,
) -> None:
    """Record bounded evidence; a suggestion never changes admission status or scope."""
    binding = session.scalar(select(SourceBinding).where(
        SourceBinding.enterprise_id == source.enterprise_id,
        SourceBinding.source_system_id == source.id,
        SourceBinding.canonical_type == kind,
        SourceBinding.external_key == f"{kind}:{external_key}",
        SourceBinding.status == "pending",
    ).with_for_update(of=SourceBinding))
    if binding is None or not anchors:
        return
    units = {item.business_unit_id for item in anchors.values()
             if item.business_unit_id is not None}
    evidence = {
        "resource_key": resource,
        "raw_manifest_id": manifest,
        "anchor_types": sorted(anchors),
    }
    retained = list(binding.suggestion_evidence or [])
    if evidence not in retained and len(retained) < 50:
        retained.append(evidence)
    binding.suggestion_evidence = retained
    binding.suggestion_evidence_count = len(retained)
    if len(units) == 1:
        target = next(iter(units))
        if binding.suggested_business_unit_id in {None, target}:
            binding.suggested_business_unit_id = target
            binding.suggestion_reason = "approved_related_dimension"
        else:
            binding.suggested_business_unit_id = None
            binding.suggestion_reason = "conflicting_related_dimensions"
    elif len(units) > 1:
        binding.suggested_business_unit_id = None
        binding.suggestion_reason = "conflicting_related_dimensions"
    binding.updated_at = observed_at


def _resolve_bindings(
    session: Session, source: ExternalSystem, references: tuple[tuple[str, str | None], ...],
    *, resource: str, manifest: str, observed_at: datetime,
) -> dict[str, SourceBinding]:
    resolved: dict[str, SourceBinding] = {}
    missing: list[tuple[str, str]] = []
    for kind, external_key in references:
        if external_key is None:
            continue
        binding = _approved_binding(session, source, kind, external_key)
        if binding is None:
            missing.append((kind, external_key))
        else:
            resolved[kind] = binding
    for kind, external_key in missing:
        _suggest_binding(session, source, kind=kind, external_key=external_key,
                         anchors=resolved, resource=resource, manifest=manifest,
                         observed_at=observed_at)
    if missing:
        raise LookupError("mapping.unassigned")
    return resolved


def _conflict(session: Session, source: ExternalSystem, resource: str,
              key: str, manifest: str, reason: str) -> None:
    identity = stable_key(source.id, resource, key, reason)
    row = session.get(MappingConflict, identity)
    if row is None:
        row = MappingConflict(id=identity, external_system_id=source.id,
                              enterprise_id=source.enterprise_id, resource_key=resource,
                              external_object_key=key[:200], status="pending", candidates=[])
        session.add(row)
    # Keep original review and each new failure distinguishable without saving raw fields.
    row.raw_manifest_id = manifest
    row.resolution = {"error_code": reason}
    row.status = "pending"


def persist_canonical_page(
    connection: Connection, *, enterprise_id: str, source_id: str,
    resource_key: str, manifest_id: str, payload: dict[str, Any],
    observed_at: datetime, scope_snapshot: dict[str, Any] | None = None,
    request_parameters: dict[str, object] | None = None,
) -> PageCounts:
    """Called inside the manifest/checkpoint transaction; never commits independently."""
    counts = PageCounts()
    with Session(bind=connection) as session:
        source = session.get(ExternalSystem, source_id)
        if source is None or source.enterprise_id != enterprise_id or source.status == "disabled":
            raise ValueError("source.scope_or_status_changed")
        if request_parameters is None:
            manifest = session.get(RawPageManifest, manifest_id)
            request_parameters = manifest.request_parameters if manifest is not None else {}
        spec = resource_spec(resource_key)
        data = response_value(payload, spec.rows_path) if spec is not None else payload.get("data")
        if not isinstance(data, list):
            data = [None]
        for index, row in enumerate(data):
            try:
                if not isinstance(row, dict):
                    raise ValueError("schema.row")
                outcome = _persist_row(session, source, resource_key, manifest_id,
                                       row, observed_at, scope_snapshot or {},
                                       request_parameters or {})
                if isinstance(outcome, PageCounts):
                    for key, value in outcome.__dict__.items():
                        setattr(counts, key, getattr(counts, key) + value)
                else:
                    setattr(counts, outcome, getattr(counts, outcome) + 1)
                if outcome == "accepted" or (isinstance(outcome, PageCounts)
                        and outcome.accepted and not outcome.stale):
                    mark_resolved(session, source, resource_key,
                                  _object_key(row, index, manifest_id,
                                              request_parameters), manifest_id)
            except LookupError:
                counts.unassigned += 1
                _conflict(session, source, resource_key, _object_key(
                    row, index, manifest_id, request_parameters),
                          manifest_id, "mapping.unassigned")
            except ValueError:
                counts.rejected += 1
                _conflict(session, source, resource_key, _object_key(
                    row, index, manifest_id, request_parameters),
                          manifest_id, "schema_or_quality_invalid")
        session.add(StagingPageResult(raw_manifest_id=manifest_id, **counts.__dict__,
                                     mapping_version=MAPPING_VERSION))
        if counts.accepted:
            source.mapping_version = MAPPING_VERSION
            source.source_schema_version = SCHEMA_VERSION
        session.flush()
    return counts


def _object_key(row: Any, index: int, manifest: str,
                request_parameters: dict[str, object] | None = None) -> str:
    # Unknown/invalid values never escape into error summaries.
    if isinstance(row, dict):
        if row.get("wo_id") is not None:
            return "fulfillment:" + stable_key(str(row["wo_id"]))
        if row.get("amazon_order_id") is not None:
            return "order:" + stable_key(str(row.get("sid", "")), str(row["amazon_order_id"]))
        if row.get("order_number") is not None and request_parameters is not None:
            return "fbm_order:" + stable_key(str(request_parameters.get("sid", "")),
                                              str(row["order_number"]))
        if "wid" in row and "product_id" in row:
            return "stock:" + stable_key(*(str(row.get(field) or "")
                for field in ("wid", "product_id", "seller_id", "fnsku")))
        for field in ("uid", "ps_id", "label_id", "providerId", "store_id", "supplier_id",
                      "statement_id", "order_sn", "pa_id", "bid", "cid", "wid", "sid", "id",
                      "marketplace_id", "product_id"):
            value = row.get(field)
            if not isinstance(value, bool) and isinstance(value, (str, int)) and str(value).strip():
                return f"{field}:{str(value)[:160]}"
    return f"row:{stable_key(manifest, str(index))}"


def _persist_row(session: Session, source: ExternalSystem, resource: str, manifest: str,
                 row: dict[str, Any], observed_at: datetime,
                 scope: dict[str, Any], request_parameters: dict[str, object] | None = None,
                 ) -> str | PageCounts:
    provenance = {
        "enterprise_id": source.enterprise_id, "external_system_id": source.id,
        "resource_key": resource, "raw_manifest_id": manifest,
        "schema_version": SCHEMA_VERSION, "mapping_version": MAPPING_VERSION,
        "observed_at": observed_at,
    }
    entity_mappers: dict[str, Callable[[dict[str, Any]], EntityInput]] = {
                      "listings": map_listing,
                      "erp_users": map_source_user,
                      "product_tags": map_product_tag, "logistics_channels": map_logistics_channel,
                      "product_styles": map_spu,
                      "shops": map_shop, "catalog.shop": map_shop, "products": map_product,
                      "brands": map_brand, "product_categories": map_category,
                      "suppliers": map_supplier,
                      "head_logistics_providers": map_head_logistics_provider,
                      "marketplaces": map_marketplace, "concept_shops": map_concept_shop,
                      "multiplatform_shops": map_multiplatform_shop,
                      "product_attributes": map_product_attribute,
                      "country_subdivisions": map_subdivision,
                      "multiplatform_subdivisions": lambda item: map_subdivision(
                          item, multiplatform=True)}
    if resource == "warehouse_bins":
        item, warehouse_external = map_warehouse_bin(row)
        warehouse = _binding(session, source, "warehouse", warehouse_external)
        _check_scope(scope, warehouse)
        identity = stable_key(source.id, item.entity_type, item.external_key)
        entity = session.get(BusinessEntity, identity)
        if entity is None:
            entity = BusinessEntity(id=identity, enterprise_id=source.enterprise_id,
                entity_type=item.entity_type, canonical_key=identity, display_name=item.name,
                status=item.status, attributes=item.attributes, updated_at=observed_at)
            session.add(entity)
        else:
            entity.display_name, entity.status = item.name, item.status
            entity.attributes, entity.updated_at = item.attributes, observed_at
        origin = session.get(CanonicalEntityOrigin, identity)
        if origin is not None and _utc(origin.observed_at) > _utc(observed_at):
            return "stale"
        if origin is None:
            origin = CanonicalEntityOrigin(id=identity, entity_id=identity,
                                           external_key=item.external_key)
            session.add(origin)
        for key, value in provenance.items():
            setattr(origin, key, value)
        origin.business_unit_id = warehouse.business_unit_id
        origin.status = "assigned"
        origin.source_updated_at = None
        return "accepted"
    if resource in entity_mappers or resource.startswith("warehouses_"):
        item = (map_warehouse(row) if resource.startswith("warehouses_") else
                entity_mappers[resource](row))
        listing_store = None
        if resource == "listings":
            listing_store = _binding(session, source, "store", str(row.get("sid", "")))
            _check_scope(scope, listing_store)
            item.attributes["store_key"] = listing_store.canonical_id
        identity = stable_key(source.id, item.entity_type, item.external_key)
        origin = session.get(CanonicalEntityOrigin, identity)
        if origin and origin.source_updated_at and item.source_updated_at:
            if _utc(origin.source_updated_at) > item.source_updated_at:
                return "stale"
        elif origin and _utc(origin.observed_at) > _utc(observed_at):
            return "stale"
        entity = session.get(BusinessEntity, identity)
        if entity is None:
            entity = BusinessEntity(id=identity, enterprise_id=source.enterprise_id,
                                    entity_type=item.entity_type, canonical_key=identity,
                                    status="unassigned")
            session.add(entity)
        entity.display_name = item.name
        entity.attributes = {**(entity.attributes or {}), **item.attributes,
                             "source_status": item.status}
        entity.updated_at = observed_at
        if listing_store is not None:
            entity.status = item.status
            session.flush()
            if origin is None:
                origin = CanonicalEntityOrigin(id=identity, entity_id=entity.id,
                                               external_key=item.external_key)
                session.add(origin)
            for key, value in provenance.items():
                setattr(origin, key, value)
            origin.business_unit_id = listing_store.business_unit_id
            origin.status = "assigned"
            origin.source_updated_at = item.source_updated_at
            return "accepted"
        if not item.requires_assignment:
            entity.status = item.status
            session.flush()
            if origin is None:
                origin = CanonicalEntityOrigin(id=identity, entity_id=entity.id,
                                               external_key=item.external_key)
                session.add(origin)
            for key, value in provenance.items():
                setattr(origin, key, value)
            origin.business_unit_id, origin.status = None, "reference"
            origin.source_updated_at = item.source_updated_at
            return "accepted"
        binding = session.scalar(select(SourceBinding).where(
            SourceBinding.source_system_id == source.id,
            SourceBinding.external_key == f"{item.entity_type}:{item.external_key}",
            SourceBinding.enterprise_id == source.enterprise_id,
        ))
        if binding is None:
            binding = SourceBinding(
                id=f"binding_{uuid4().hex}", enterprise_id=source.enterprise_id,
                business_unit_id=None, source_system_id=source.id,
                external_key=f"{item.entity_type}:{item.external_key}",
                canonical_type=item.entity_type, canonical_id=identity,
                mapping_version=MAPPING_VERSION, status="pending",
                created_at=observed_at, updated_at=observed_at,
            )
            session.add(binding)
        assigned = binding.status == "approved" and binding.business_unit_id is not None
        entity.status = item.status if assigned else "unassigned"
        session.flush()
        if origin is None:
            origin = CanonicalEntityOrigin(id=identity, entity_id=entity.id,
                                           external_key=item.external_key)
            session.add(origin)
        for key, value in provenance.items():
            setattr(origin, key, value)
        origin.business_unit_id = binding.business_unit_id if assigned else None
        origin.source_updated_at = item.source_updated_at
        origin.status = "assigned" if assigned else "unassigned"
        return "accepted"
    if resource == "fulfillments":
        shipment = map_fulfillment(row)
        dimensions = _resolve_bindings(session, source, (
            ("store", shipment.store_external_key),
            ("warehouse", shipment.warehouse_external_key),
        ), resource=resource, manifest=manifest, observed_at=observed_at)
        shipment_store = dimensions["store"]
        shipment_warehouse = dimensions["warehouse"]
        _check_scope(scope, shipment_store)
        _check_scope(scope, shipment_warehouse)
        if shipment_store.business_unit_id != shipment_warehouse.business_unit_id:
            raise LookupError("mapping.project_conflict")
        identity = stable_key(source.id, resource, shipment.external_key)
        current_shipment = session.get(CanonicalFulfillment, identity)
        if current_shipment is not None:
            previous_local = current_shipment.source_updated_local_time
            incoming_local = shipment.source_updated_local_time
            if previous_local > incoming_local or (previous_local == incoming_local
                    and _utc(current_shipment.observed_at) > _utc(observed_at)):
                return "stale"
        else:
            current_shipment = CanonicalFulfillment(id=identity)
            session.add(current_shipment)
        values = {**provenance, **shipment.model_dump(exclude={"lines", "store_external_key",
                   "warehouse_external_key"}), "store_key": shipment_store.canonical_id,
                  "warehouse_key": shipment_warehouse.canonical_id,
                  "business_unit_id": shipment_store.business_unit_id}
        for key, value in values.items():
            setattr(current_shipment, key, value)
        session.flush()
        session.execute(delete(CanonicalFulfillmentLine).where(
            CanonicalFulfillmentLine.fulfillment_id == identity))
        for shipment_line in shipment.lines:
            session.add(CanonicalFulfillmentLine(
                id=stable_key(identity, shipment_line.external_key),
                fulfillment_id=identity, **shipment_line.model_dump()))
        return "accepted"
    if resource == "after_sales":
        binding = _binding(session, source, "store", str(row.get("sid", "")))
        _check_scope(scope, binding)
        store_entity = session.scalar(select(BusinessEntity).where(
            BusinessEntity.enterprise_id == source.enterprise_id,
            BusinessEntity.canonical_key == binding.canonical_id))
        timezone = (store_entity.attributes.get("timezone") if store_entity else None)
        # Validate every child before mutating any existing fact.
        children = map_after_sales(row, timezone=timezone if isinstance(timezone, str) else None)
        result = PageCounts()
        for child in children:
            identity = stable_key(source.id, resource, child.external_key)
            event = session.get(CanonicalAfterSale, identity)
            if event is not None:
                previous = datetime.fromisoformat(event.source_updated_local_time)
                incoming = datetime.fromisoformat(child.source_updated_local_time)
                if (previous.tzinfo is None) != (incoming.tzinfo is None):
                    _conflict(session, source, resource, child.external_key, manifest,
                              "source_time_comparison_pending")
                    result.stale += 1
                    continue
                if previous > incoming:
                    result.stale += 1
                    continue
            else:
                event = CanonicalAfterSale(id=identity)
                session.add(event)
            values = {**provenance, **child.model_dump(exclude={"store_external_key"}),
                      "store_key": binding.canonical_id,
                      "business_unit_id": binding.business_unit_id}
            for key, value in values.items():
                setattr(event, key, value)
            if child.quality_flags:
                _conflict(session, source, resource, child.external_key, manifest,
                          "normalization_pending")
            else:
                mark_resolved(session, source, resource, child.external_key, manifest)
            result.accepted += 1
        return result
    if resource == "orders":
        order = map_order(row)
        binding = _binding(session, source, "store", order.store_external_key)
        _check_scope(scope, binding)
        identity = stable_key(source.id, resource, order.store_external_key, order.external_key)
        current = session.get(CanonicalSalesOrder, identity)
        if current and current.source_updated_at:
            if _utc(current.source_updated_at) > order.source_updated_at:
                return "stale"
        if current is None:
            current = CanonicalSalesOrder(id=identity)
            session.add(current)
        values = {**provenance, **order.model_dump(exclude={"lines", "store_external_key"}),
                  "external_key": f"{order.store_external_key}:{order.external_key}",
                  "store_key": binding.canonical_id, "business_unit_id": binding.business_unit_id}
        with session.no_autoflush:
            store_entity = session.scalar(select(BusinessEntity).where(
                BusinessEntity.enterprise_id == source.enterprise_id,
                BusinessEntity.canonical_key == binding.canonical_id,
            ))
        if store_entity and isinstance(store_entity.attributes.get("timezone"), str):
            values["store_timezone"] = store_entity.attributes["timezone"]
        for key, value in values.items():
            setattr(current, key, value)
        session.flush()
        # Complete validated order row is the only boundary allowed to replace its lines.
        session.execute(delete(CanonicalSalesOrderLine).where(
            CanonicalSalesOrderLine.order_id == identity
        ))
        for ordinal, line in enumerate(order.lines):
            line_key = stable_key(line.sku, str(ordinal))
            session.add(CanonicalSalesOrderLine(id=stable_key(identity, line_key),
                        order_id=identity, line_key=line_key, **line.model_dump()))
        return "accepted"
    if resource == "inventory":
        stock = map_stock(row)
        dimensions = _resolve_bindings(session, source, (
            ("store", stock.store_external_key),
            ("warehouse", stock.warehouse_external_key),
            ("product", stock.product_external_key),
        ), resource=resource, manifest=manifest, observed_at=observed_at)
        warehouse = dimensions["warehouse"]
        product = dimensions["product"]
        _check_scope(scope, warehouse)
        if product.business_unit_id != warehouse.business_unit_id:
            raise LookupError("mapping.project_conflict")
        store = dimensions.get("store")
        if store is not None:
            _check_scope(scope, store)
        elif scope.get("scope_level") == "store":
            raise LookupError("mapping.scope_mismatch")
        if store and store.business_unit_id != warehouse.business_unit_id:
            raise LookupError("mapping.project_conflict")
        identity = stable_key(source.id, resource, stock.external_key)
        current_stock = session.get(CanonicalInventoryBalance, identity)
        if current_stock and _utc(current_stock.observed_at) > observed_at:
            return "stale"
        if current_stock is None:
            current_stock = CanonicalInventoryBalance(id=identity)
            session.add(current_stock)
        values = {**provenance, **stock.model_dump(exclude={"warehouse_external_key",
                   "product_external_key", "store_external_key"}),
                  "warehouse_key": warehouse.canonical_id, "product_key": product.canonical_id,
                  "store_key": store.canonical_id if store else None,
                  "business_unit_id": warehouse.business_unit_id}
        for key, value in values.items():
            setattr(current_stock, key, value)
        return "accepted"
    operational_mappers: dict[str, Callable[[], OperationalFactInput]] = {
        "monthly_exchange_rates": lambda: map_exchange_rate(row),
        "fbm_orders": lambda: map_fbm_order(row, request_parameters or {}),
        "fba_shipments": lambda: map_fba_shipment(row),
        "inbound_orders": lambda: map_inventory_document(row, "inbound"),
        "outbound_orders": lambda: map_inventory_document(row, "outbound"),
        "inventory_statements": lambda: map_inventory_statement(row),
        "fba_inventory": lambda: map_fba_inventory(row),
        "purchases": lambda: map_purchase_order(row),
        "advertising": lambda: map_ad_campaign(row, request_parameters or {}),
        "finance": lambda: map_finance_fee(row, request_parameters or {}),
        "customer_service": lambda: map_customer_review(row, request_parameters or {}),
        "source_reports": lambda: map_source_order(row, request_parameters or {}),
    }
    if resource in operational_mappers:
        operational_item = operational_mappers[resource]()
        return _persist_operational_fact(session, source, resource, manifest, operational_item,
                                         observed_at, scope, provenance)
    raise ValueError("schema.pending")


def _persist_operational_fact(session: Session, source: ExternalSystem, resource: str,
                              manifest: str, item: OperationalFactInput,
                              observed_at: datetime, scope: dict[str, Any],
                              provenance: dict[str, Any]) -> str:
    bindings = _resolve_bindings(session, source, (
        ("store", item.store_external_key),
        ("warehouse", item.warehouse_external_key),
        ("product", item.product_external_key),
    ), resource=resource, manifest=manifest, observed_at=observed_at)
    for binding in bindings.values():
        _check_scope(scope, binding)
    units = {binding.business_unit_id for binding in bindings.values()}
    if len(units) > 1:
        raise LookupError("mapping.project_conflict")
    business_unit_id = next(iter(units), None)
    if source.business_unit_id is not None and business_unit_id not in {
        None, source.business_unit_id
    }:
        raise LookupError("mapping.source_project_conflict")
    identity = stable_key(source.id, resource, item.external_key)
    fact = session.get(CanonicalOperationalFact, identity)
    if fact is not None and _utc(fact.observed_at) > _utc(observed_at):
        return "stale"
    if fact is None:
        fact = CanonicalOperationalFact(id=identity)
        session.add(fact)
    timezone = None
    store = bindings.get("store")
    if store is not None:
        with session.no_autoflush:
            store_entity = session.scalar(select(BusinessEntity).where(
                BusinessEntity.enterprise_id == source.enterprise_id,
                BusinessEntity.canonical_key == store.canonical_id))
        if store_entity is not None and isinstance(store_entity.attributes.get("timezone"), str):
            timezone = store_entity.attributes["timezone"]
    store_binding = bindings.get("store")
    warehouse_binding = bindings.get("warehouse")
    product_binding = bindings.get("product")
    values = {**provenance, **item.model_dump(exclude={"store_external_key",
        "warehouse_external_key", "product_external_key"}),
        "business_unit_id": business_unit_id,
        "store_key": store_binding.canonical_id if store_binding is not None else None,
        "warehouse_key": (warehouse_binding.canonical_id
                          if warehouse_binding is not None else None),
        "product_key": (product_binding.canonical_id
                        if product_binding is not None else None),
        "source_timezone": timezone}
    for key, value in values.items():
        setattr(fact, key, value)
    if item.quality_flags:
        _conflict(session, source, resource, item.external_key, manifest,
                  "normalization_pending")
    return "accepted"


def _check_scope(scope: dict[str, Any], binding: SourceBinding) -> None:
    units = scope.get("business_unit_ids")
    if units is not None and binding.business_unit_id not in units:
        raise LookupError("mapping.scope_mismatch")
    stores = scope.get("store_ids")
    if (stores is not None and binding.canonical_type == "store"
            and binding.canonical_id not in stores):
        raise LookupError("mapping.scope_mismatch")
    warehouses = scope.get("warehouse_ids")
    if (warehouses is not None and binding.canonical_type == "warehouse"
            and binding.canonical_id not in warehouses):
        raise LookupError("mapping.scope_mismatch")
