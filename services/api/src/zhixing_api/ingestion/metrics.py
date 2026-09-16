"""Current authoritative order observations; never payment or revenue metrics."""

from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, select

from zhixing_api.data_models import CanonicalSalesOrder as Order
from zhixing_api.database import Database
from zhixing_api.scope_context import ScopeContext

from .authority import authority_condition


class OrderSummaryLineage(BaseModel):
    enterprise_id: str
    business_unit_id: str
    external_system_id: str
    resource_key: str
    schema_version: str
    mapping_version: str
    order_count: int
    data_as_of: datetime


class OrderSummary(BaseModel):
    schema_version: Literal[1] = 1
    definition_version: Literal["canonical-orders-v1"] = "canonical-orders-v1"
    authority_applied: Literal[True] = True
    scope_snapshot: dict[str, object]
    date_from: date
    date_to_exclusive: date
    order_count: int
    status_counts: dict[str, int]
    currency_totals: dict[str, Decimal]
    missing_amount_count: int
    base_amount: Decimal | None = None
    data_as_of: datetime | None
    quality_flags: list[str]
    lineage: list[OrderSummaryLineage]


def summarize_orders(database: Database, scope: ScopeContext,
                     date_from: date, date_to: date) -> OrderSummary:
    if date_to <= date_from:
        raise ValueError("date_to must be after date_from")
    filters = [
        Order.enterprise_id.in_(set(scope.selected_enterprise_ids)
                                & set(scope.allowed_enterprise_ids)),
        Order.business_unit_id.in_(scope.business_unit_ids),
        Order.store_key.in_(scope.store_ids),
        Order.business_date >= date_from, Order.business_date < date_to,
        authority_condition(Order, "orders"),
    ]
    # One SQL statement keeps counts, amounts and lineage on the same database snapshot.
    dimensions = (Order.enterprise_id, Order.business_unit_id, Order.external_system_id,
                  Order.resource_key, Order.schema_version, Order.mapping_version,
                  Order.status, Order.currency_code, Order.amount.is_not(None))
    statement = select(*dimensions, func.count(), func.sum(Order.amount),
                       func.max(Order.observed_at)).where(*filters).group_by(*dimensions)
    count, missing = 0, 0
    currencies: dict[str, Decimal] = {}
    statuses: dict[str, int] = {}
    lineage: dict[tuple[str, ...], OrderSummaryLineage] = {}
    latest: datetime | None = None
    with database.session() as session:
        for row in session.execute(statement):
            legal, unit, source, resource, schema, mapping, status, currency, has_amount = row[:9]
            number, amount, observed = row[9:]
            count += number
            statuses[status] = statuses.get(status, 0) + number
            if not has_amount or not currency:
                missing += number
            else:
                with localcontext() as context:
                    context.prec = 50
                    currencies[currency] = currencies.get(currency, Decimal(0)) + amount
            latest = max(latest, observed) if latest else observed
            key = (legal, unit, source, resource, schema, mapping)
            if key not in lineage:
                lineage[key] = OrderSummaryLineage(enterprise_id=legal, business_unit_id=unit,
                    external_system_id=source, resource_key=resource, schema_version=schema,
                    mapping_version=mapping, order_count=0, data_as_of=observed)
            lineage[key].order_count += number
            lineage[key].data_as_of = max(lineage[key].data_as_of, observed)
    flags = ["coverage_unverified", "fx_unavailable"]
    if not count:
        flags.append("no_authoritative_orders")
    if missing:
        flags.append("amount_or_currency_missing")
    if scope.scope_level == "group":
        flags.append("intercompany_elimination_unavailable")
    snapshot = scope.snapshot()
    snapshot["data_as_of"] = latest.isoformat() if latest else None
    return OrderSummary(scope_snapshot=snapshot, date_from=date_from,
        date_to_exclusive=date_to, order_count=count, status_counts=statuses,
        currency_totals=currencies, missing_amount_count=missing, data_as_of=latest,
        quality_flags=flags, lineage=[lineage[key] for key in sorted(lineage)])
