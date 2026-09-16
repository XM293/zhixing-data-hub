"""Read-only sales outbound observations; never infer revenue or stock movements."""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from .mapping import _integer, _required


class FulfillmentLineInput(BaseModel):
    external_key: str
    product_external_key: str
    sku: str
    quantity: int
    bundle_type: int
    parent_external_key: str | None


class FulfillmentInput(BaseModel):
    external_key: str
    shipment_number: str
    store_external_key: str
    warehouse_external_key: str
    order_external_key: str
    platform_order_keys: list[str]
    status: str
    logistics_status: int
    freight_amount: Decimal | None
    freight_currency_code: str | None
    source_local_time: str
    source_updated_local_time: str
    dispatched_local_time: str | None
    business_date: date
    source_timezone: str | None = None
    created_at: datetime | None = None
    dispatched_at: datetime | None = None
    source_updated_at: datetime | None = None
    quality_flags: list[str]
    lines: list[FulfillmentLineInput]


def _positive_id(row: dict[str, Any], key: str) -> str:
    value = _integer(row, key)
    if value <= 0 or len(str(value)) > 20:
        raise ValueError("schema.fulfillment_id")
    return str(value)


def _source_time(value: str) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
        raise ValueError("schema.fulfillment_time")
    return datetime.fromisoformat(value)


def _text(row: dict[str, Any], key: str, maximum: int = 200) -> str:
    value = _required(row, key)
    if len(value) > maximum:
        raise ValueError("schema.fulfillment_text")
    return value


def map_fulfillment(row: dict[str, Any]) -> FulfillmentInput:
    status = _integer(row, "status")
    statuses = {1: "logistics_ordering", 2: "awaiting_dispatch", 3: "dispatched", 4: "intercepted"}
    logistics = _integer(row, "logistics_status")
    if status not in statuses or logistics not in {1, 2, 3, 4, 5, 6, 7, 11, 41, 42, 43}:
        raise ValueError("schema.fulfillment_status")
    local, updated = _required(row, "create_at"), _required(row, "update_at")
    business_date = _source_time(local).date()
    _source_time(updated)
    dispatched = row.get("delivered_at") or None
    if dispatched is not None:
        if not isinstance(dispatched, str):
            raise ValueError("schema.fulfillment_time")
        _source_time(dispatched)
    flags = ["source_timezone_pending"]
    raw_amount = row.get("logistics_freight")
    amount = None
    if raw_amount not in (None, ""):
        if isinstance(raw_amount, bool) or not re.fullmatch(r"-?\d+(?:\.\d+)?", str(raw_amount)):
            raise ValueError("schema.fulfillment_freight")
        amount = Decimal(str(raw_amount))
        exponent = amount.as_tuple().exponent
        if not isinstance(exponent, int) or exponent < -12 or amount.adjusted() >= 26:
            raise ValueError("schema.fulfillment_freight")
    raw_currency = row.get("logistics_freight_currency_code")
    currency = (raw_currency if isinstance(raw_currency, str)
                and re.fullmatch(r"[A-Z]{3}", raw_currency) else None)
    if amount is not None and currency is None:
        flags.append("freight_currency_pending")
    platform_keys = row.get("platform_order_no")
    if not isinstance(platform_keys, list) or any(
            not isinstance(key, str) or not key.strip() or len(key) > 200 for key in platform_keys):
        raise ValueError("schema.fulfillment_order_keys")
    items = row.get("product_info")
    if not isinstance(items, list):
        raise ValueError("schema.fulfillment_lines")
    lines: list[FulfillmentLineInput] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("schema.fulfillment_line")
        key = _positive_id(item, "wod_id")
        quantity, bundle = _integer(item, "count"), _integer(item, "bundle_type")
        if key in seen or not 0 <= quantity <= 9223372036854775807 or bundle not in {0, 1, 2}:
            raise ValueError("schema.fulfillment_line")
        seen.add(key)
        parent = _positive_id(item, "bundle_wod_id") if bundle == 2 else None
        if parent == key:
            raise ValueError("schema.fulfillment_bundle")
        lines.append(FulfillmentLineInput(external_key=key,
            product_external_key=_positive_id(item, "product_id"), sku=_text(item, "sku", 160),
            quantity=quantity, bundle_type=bundle, parent_external_key=parent))
    parents = {line.external_key for line in lines if line.bundle_type == 1}
    if any(line.parent_external_key not in parents for line in lines if line.bundle_type == 2):
        raise ValueError("schema.fulfillment_bundle")
    return FulfillmentInput(external_key=_positive_id(row, "wo_id"),
        shipment_number=_text(row, "wo_number"), store_external_key=_positive_id(row, "sid"),
        warehouse_external_key=_positive_id(row, "wid"),
        order_external_key=_text(row, "order_number"), platform_order_keys=platform_keys,
        status=statuses[status], logistics_status=logistics, freight_amount=amount,
        freight_currency_code=currency, source_local_time=local, source_updated_local_time=updated,
        dispatched_local_time=dispatched, business_date=business_date, quality_flags=flags,
        lines=lines)
