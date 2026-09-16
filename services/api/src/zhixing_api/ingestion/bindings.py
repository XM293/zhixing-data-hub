from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, select

from zhixing_api.data_models import (
    BusinessEntity,
    BusinessUnit,
    CanonicalAfterSale,
    CanonicalEntityOrigin,
    CanonicalFulfillment,
    CanonicalInventoryBalance,
    CanonicalSalesOrder,
    ExternalSystem,
    PlatformEvent,
    SourceBinding,
)
from zhixing_api.database import Database
from zhixing_api.errors import ApiProblem


def review_binding(
    database: Database, *, enterprise_id: str, source_key: str, binding_id: str,
    principal_id: str, status: str, business_unit_id: str | None = None,
    store_timezone: str | None = None,
) -> SourceBinding:
    if status not in {"approved", "rejected"}:
        raise ApiProblem(status_code=422, code="source.binding_status_invalid",
                         message="审核状态无效")
    if store_timezone:
        try:
            ZoneInfo(store_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ApiProblem(status_code=422, code="source.timezone_invalid",
                             message="店铺时区无效") from None
    with database.session() as session:
        binding = session.scalar(select(SourceBinding).join(
            ExternalSystem, ExternalSystem.id == SourceBinding.source_system_id
        ).where(SourceBinding.id == binding_id, SourceBinding.enterprise_id == enterprise_id,
                ExternalSystem.enterprise_id == enterprise_id,
                ExternalSystem.system_key == source_key).with_for_update())
        if binding is None:
            raise ApiProblem(status_code=404, code="source.binding_not_found", message="映射不存在")
        target = business_unit_id or binding.business_unit_id
        entity = session.scalar(select(BusinessEntity).where(
            BusinessEntity.enterprise_id == enterprise_id,
            BusinessEntity.entity_type == binding.canonical_type,
            BusinessEntity.canonical_key == binding.canonical_id,
        ))
        listings = list(session.execute(select(BusinessEntity, CanonicalEntityOrigin).join(
            CanonicalEntityOrigin, CanonicalEntityOrigin.entity_id == BusinessEntity.id
        ).where(
            BusinessEntity.enterprise_id == enterprise_id,
            BusinessEntity.entity_type == "listing",
            BusinessEntity.attributes["store_key"].as_string() == binding.canonical_id,
            CanonicalEntityOrigin.enterprise_id == enterprise_id,
            CanonicalEntityOrigin.external_system_id == binding.source_system_id,
            CanonicalEntityOrigin.resource_key == "listings",
        ))) if binding.canonical_type == "store" else []
        if status == "approved":
            unit = session.scalar(select(BusinessUnit).where(
                BusinessUnit.id == target, BusinessUnit.enterprise_id == enterprise_id,
                BusinessUnit.status == "active",
            ))
            if unit is None or entity is None:
                raise ApiProblem(status_code=422, code="source.binding_scope_invalid",
                                 message="请选择当前法人的有效业务单元和业务实体")
        # Reassigning an admitted dimension needs an explicit historical migration.
        if target != binding.business_unit_id:
            used_order = session.scalar(select(CanonicalSalesOrder.id).where(
                CanonicalSalesOrder.external_system_id == binding.source_system_id,
                CanonicalSalesOrder.store_key == binding.canonical_id,
            ).limit(1))
            used_stock = session.scalar(select(CanonicalInventoryBalance.id).where(
                CanonicalInventoryBalance.external_system_id == binding.source_system_id,
                or_(CanonicalInventoryBalance.store_key == binding.canonical_id,
                    CanonicalInventoryBalance.warehouse_key == binding.canonical_id,
                    CanonicalInventoryBalance.product_key == binding.canonical_id),
            ).limit(1))
            used_after_sale = session.scalar(select(CanonicalAfterSale.id).where(
                CanonicalAfterSale.external_system_id == binding.source_system_id,
                CanonicalAfterSale.store_key == binding.canonical_id,
            ).limit(1))
            used_fulfillment = session.scalar(select(CanonicalFulfillment.id).where(
                CanonicalFulfillment.external_system_id == binding.source_system_id,
                or_(CanonicalFulfillment.store_key == binding.canonical_id,
                    CanonicalFulfillment.warehouse_key == binding.canonical_id),
            ).limit(1))
            if used_order or used_stock or used_after_sale or used_fulfillment or listings:
                raise ApiProblem(status_code=409, code="source.binding_has_facts",
                                 message="映射已有关联事实，请先完成历史归属迁移")
        now = datetime.now(UTC)
        binding.business_unit_id = target
        binding.status, binding.updated_at = status, now
        if entity is not None:
            entity.status = (str(entity.attributes.get("source_status") or "active")
                             if status == "approved" else "unassigned")
            entity.updated_at = now
            if store_timezone and binding.canonical_type == "store":
                entity.attributes = {**entity.attributes, "timezone": store_timezone}
            for origin in session.scalars(select(CanonicalEntityOrigin).where(
                CanonicalEntityOrigin.entity_id == entity.id,
                CanonicalEntityOrigin.external_system_id == binding.source_system_id,
            )):
                origin.business_unit_id = target if status == "approved" else None
                origin.status = "assigned" if status == "approved" else "unassigned"
        for listing, listing_origin in listings:
            listing.status = (str(listing.attributes.get("source_status") or "unknown")
                              if status == "approved" else "unassigned")
            listing.updated_at = now
            listing_origin.business_unit_id = target if status == "approved" else None
            listing_origin.status = "assigned" if status == "approved" else "unassigned"
        session.add(PlatformEvent(id=f"evt_{uuid4().hex}", enterprise_id=enterprise_id,
                    event_type="source.binding.reviewed", severity="info", title="来源归属审核",
                    detail=f"{principal_id}:{binding.id}:{status}:{target or ''}", occurred_at=now))
        session.commit()
        session.refresh(binding)
        session.expunge(binding)
        return binding
