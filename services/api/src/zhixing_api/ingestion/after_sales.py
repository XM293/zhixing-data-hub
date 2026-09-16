"""Typed after-sale events without inferring a currency from a symbol or UTC from local time."""
import hashlib
import json
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from .mapping import _integer, _required


class AfterSaleInput(BaseModel):
    external_key: str
    source_item_key: str
    store_external_key: str
    order_external_key: str
    sku: str
    after_type: str
    quantity: int
    status: str | None
    source_amount_text: str
    amount: Decimal | None
    currency_code: str | None
    source_local_time: str
    source_updated_local_time: str
    occurred_at: datetime | None
    source_updated_at: datetime | None
    business_date: date
    store_timezone: str | None
    quality_flags: list[str]


def local_to_utc(value: str, timezone: str | None) -> datetime | None:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC)
    if not timezone:
        return None
    zone = ZoneInfo(timezone)
    first, second = parsed.replace(tzinfo=zone, fold=0), parsed.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second.utcoffset():
        return None
    result = first.astimezone(UTC)
    if result.astimezone(zone).replace(tzinfo=None) != parsed:
        return None
    return result


def map_after_sales(row: dict[str, Any], *, timezone: str | None = None) -> list[AfterSaleInput]:
    store, order = _required(row, "sid"), _required(row, "amazon_order_id")
    children = row.get("item_list")
    if not isinstance(children, list) or not children:
        raise ValueError("schema.after_sale_items")
    result = []
    seen: set[str] = set()
    for child in children:
        if not isinstance(child, dict):
            raise ValueError("schema.after_sale_item")
        key = _required(child, "item_identifier")
        if key in seen:
            raise ValueError("schema.after_sale_duplicate")
        seen.add(key)
        kind = {"退款": "refund", "退货": "return", "换货": "replacement"}.get(
            _required(child, "after_type"))
        if kind is None:
            raise ValueError("schema.after_sale_type")
        quantity = _integer(child, "after_quantity")
        if quantity < 0:
            raise ValueError("schema.after_sale_quantity")
        local, updated = _required(child, "after_time"), _required(child, "data_update_time")
        occurred_at, updated_at = local_to_utc(local, timezone), local_to_utc(updated, timezone)
        amount_text = str(child.get("refund_amount") or "")
        match = re.fullmatch(r"([+-]?)([A-Za-z$€£¥￥]*)(\d+(?:\.\d+)?)", amount_text.strip())
        amount = Decimal(match[1] + match[3]) if match else None
        currency = match[2] if match and re.fullmatch(r"[A-Z]{3}", match[2]) else None
        if amount is not None:
            exponent = amount.as_tuple().exponent
            if not isinstance(exponent, int) or exponent < -12 or amount.adjusted() >= 26:
                amount = None
        flags = []
        if kind == "refund" or amount_text:
            if currency is None:
                flags.append("currency_pending")
            if amount is None:
                flags.append("amount_format_pending")
        if occurred_at is None or updated_at is None:
            flags.append("timezone_pending")
        identity = hashlib.sha256(json.dumps([store, key], ensure_ascii=False).encode()).hexdigest()
        result.append(AfterSaleInput(external_key=identity, source_item_key=key,
            store_external_key=store, order_external_key=order, sku=_required(child, "msku"),
            after_type=kind, quantity=quantity,
            status=str(child.get("return_status") or "") or None,
            source_amount_text=amount_text, amount=amount, currency_code=currency,
            source_local_time=local, source_updated_local_time=updated,
            occurred_at=occurred_at, source_updated_at=updated_at,
            business_date=datetime.fromisoformat(local).date(), store_timezone=timezone,
            quality_flags=flags))
    return result
