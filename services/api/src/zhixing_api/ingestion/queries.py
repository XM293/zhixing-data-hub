from datetime import date
from typing import Any, Literal, cast

from sqlalchemy import func, or_, select
from sqlalchemy.sql.elements import ColumnElement

from zhixing_api.data_models import (
    CanonicalAfterSale,
    CanonicalFulfillment,
    CanonicalFulfillmentLine,
    CanonicalInventoryBalance,
    CanonicalOperationalFact,
    CanonicalSalesOrder,
)
from zhixing_api.database import Database
from zhixing_api.scope_context import ScopeContext

from .authority import authority_condition
from .read_models import (
    AfterSaleView,
    CanonicalPage,
    FulfillmentLineView,
    FulfillmentView,
    InventoryBalanceView,
    OperationalFactView,
    SalesOrderView,
)


def canonical_page(
    database: Database, scope: ScopeContext,
    family: Literal["orders", "inventory", "after_sales", "fulfillments", "operational"], *,
    offset: int = 0, limit: int = 50, authoritative_only: bool = False,
    source_id: str | None = None, business_unit_id: str | None = None,
    resource_key: str | None = None, schema_version: str | None = None,
    mapping_version: str | None = None, date_from: date | None = None,
    date_to: date | None = None,
) -> CanonicalPage:
    model: Any = (CanonicalSalesOrder if family == "orders" else
             CanonicalFulfillment if family == "fulfillments" else
             CanonicalAfterSale if family == "after_sales" else CanonicalInventoryBalance)
    if family == "operational":
        model = CanonicalOperationalFact
    filters: list[ColumnElement[bool]] = [
        model.enterprise_id.in_(set(scope.selected_enterprise_ids)
                                & set(scope.allowed_enterprise_ids)),
        (or_(model.business_unit_id.is_(None),
             model.business_unit_id.in_(scope.business_unit_ids))
         if model is CanonicalOperationalFact else
         model.business_unit_id.in_(scope.business_unit_ids)),
    ]
    for column, value in ((model.external_system_id, source_id),
                          (model.business_unit_id, business_unit_id),
                          (model.resource_key, resource_key),
                          (model.schema_version, schema_version),
                          (model.mapping_version, mapping_version)):
        if value is not None:
            filters.append(column == value)
    if date_from and date_to and date_to <= date_from:
        raise ValueError("date_to must be after date_from")
    if model is CanonicalInventoryBalance and (date_from or date_to):
        raise ValueError("inventory has no business date interval")
    if authoritative_only and model is CanonicalOperationalFact:
        raise ValueError("operational facts require a resource filter instead of one authority")
    if authoritative_only:
        filters.append(authority_condition(model, cast(Any, family)))
    if model is CanonicalSalesOrder or model is CanonicalAfterSale or model is CanonicalFulfillment:
        filters.append(model.store_key.in_(scope.store_ids))
        if date_from:
            filters.append(model.business_date >= date_from)
        if date_to:
            filters.append(model.business_date < date_to)
        if model is CanonicalFulfillment:
            filters.append(model.warehouse_key.in_(scope.warehouse_ids))
    elif model is CanonicalInventoryBalance:
        filters.append(CanonicalInventoryBalance.warehouse_key.in_(scope.warehouse_ids))
        filters.append(CanonicalInventoryBalance.store_key.in_(scope.store_ids)
                       if scope.scope_level == "store" else or_(
                           CanonicalInventoryBalance.store_key.is_(None),
                           CanonicalInventoryBalance.store_key.in_(scope.store_ids)))
    else:
        filters.append(or_(CanonicalOperationalFact.store_key.is_(None),
                           CanonicalOperationalFact.store_key.in_(scope.store_ids)))
        filters.append(or_(CanonicalOperationalFact.warehouse_key.is_(None),
                           CanonicalOperationalFact.warehouse_key.in_(scope.warehouse_ids)))
        if date_from:
            filters.append(CanonicalOperationalFact.business_date >= date_from)
        if date_to:
            filters.append(CanonicalOperationalFact.business_date < date_to)
    with database.session() as session:
        total = int(session.scalar(select(func.count()).select_from(model).where(*filters)) or 0)
        latest = session.scalar(select(func.max(model.observed_at)).where(*filters))
        rows = session.scalars(select(model).where(*filters)
                               .order_by(model.observed_at.desc(), model.id)
                               .offset(offset).limit(limit)).all()
        shipment_views: dict[str, FulfillmentView] = {}
        if model is CanonicalFulfillment:
            shipment_views = {row.id: FulfillmentView.model_validate(row) for row in rows
                              if isinstance(row, CanonicalFulfillment)}
            for line in session.scalars(select(CanonicalFulfillmentLine).where(
                    CanonicalFulfillmentLine.fulfillment_id.in_(shipment_views))
                    .order_by(CanonicalFulfillmentLine.external_key)):
                shipment_views[line.fulfillment_id].lines.append(
                    FulfillmentLineView.model_validate(line))
        return CanonicalPage(
            scope_snapshot=scope.snapshot(), total=total, offset=offset, limit=limit,
            data_as_of=latest,
            authority_applied=authoritative_only,
            items=[SalesOrderView.model_validate(row) if isinstance(row, CanonicalSalesOrder)
                   else AfterSaleView.model_validate(row) if isinstance(row, CanonicalAfterSale)
                   else shipment_views[row.id] if isinstance(row, CanonicalFulfillment)
                   else OperationalFactView.model_validate(row)
                   if isinstance(row, CanonicalOperationalFact)
                   else InventoryBalanceView.model_validate(row) for row in rows],
        )
