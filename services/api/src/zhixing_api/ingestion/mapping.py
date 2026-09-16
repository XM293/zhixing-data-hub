from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict

SCHEMA_VERSION = "lingxing-2026-09-10"
MAPPING_VERSION = "2.5.0"


class EntityInput(BaseModel):
    entity_type: str
    external_key: str
    name: str
    status: str
    attributes: dict[str, Any]
    source_updated_at: datetime | None = None
    requires_assignment: bool = True


class OrderLineInput(BaseModel):
    sku: str
    local_sku: str | None = None
    quantity: int


class OrderInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    external_key: str
    store_external_key: str
    status: str
    amount: Decimal | None
    currency_code: str | None
    ordered_at: datetime
    source_local_time: str
    business_date: date
    source_updated_at: datetime
    fulfillment_channel: str | None
    lines: list[OrderLineInput]


class StockInput(BaseModel):
    external_key: str
    warehouse_external_key: str
    product_external_key: str
    sku: str
    store_external_key: str | None
    total: int
    available: int
    defective: int
    inspecting: int
    reserved: int
    in_transit: int | None


def _required(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or isinstance(value, (bool, list, dict)) or not str(value).strip():
        raise ValueError(f"schema.required:{key}")
    return str(value)


def _nullable_text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"schema.text:{key}")
    return value.strip() or None


def _integer(row: dict[str, Any], key: str) -> int:
    raw = _required(row, key)
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"schema.integer:{key}") from None


def _utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("schema.timestamp") from None
    # Only fields explicitly documented as UTC may use this parser.
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def map_product_tag(row: dict[str, Any]) -> EntityInput:
    return EntityInput(entity_type="product_tag", external_key=_required(row, "label_id"),
                       name=_required(row, "label_name"), status="unknown", attributes={})


def map_listing(row: dict[str, Any]) -> EntityInput:
    sid = _integer(row, "sid")
    sku = _required(row, "seller_sku")
    source_name = row.get("item_name")
    if source_name is not None and not isinstance(source_name, str):
        raise ValueError("schema.listing_name")
    name = source_name.strip() if source_name and source_name.strip() else sku
    status, deleted = _integer(row, "status"), _integer(row, "is_delete")
    if sid <= 0 or status not in {0, 1} or deleted not in {0, 1}:
        raise ValueError("schema.listing_state")
    attributes: dict[str, Any] = {"store_external_key": str(sid), "seller_sku": sku}
    for key in ("local_sku", "asin", "fnsku"):
        value = row.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError("schema.listing_reference")
        attributes[key] = value or None
    updated = row.get("listing_update_date")
    return EntityInput(entity_type="listing",
        external_key=json.dumps([str(sid), sku], ensure_ascii=False, separators=(",", ":")),
        name=name,
        status="deleted" if deleted else "active" if status else "inactive",
        attributes=attributes,
        source_updated_at=_utc(str(updated)) if updated else None)


def map_spu(row: dict[str, Any]) -> EntityInput:
    identity, status = _integer(row, "ps_id"), _integer(row, "status")
    states = {0: "discontinued", 1: "on_sale", 2: "developing", 3: "clearance"}
    if identity <= 0 or status not in states:
        raise ValueError("schema.product_style")
    return EntityInput(entity_type="product_style", external_key=str(identity),
        name=_required(row, "spu_name"), status=states[status],
        attributes={"spu": _required(row, "spu"),
            "category_external_key": _required(row, "cid"),
            "brand_external_key": _required(row, "bid"),
            "developer_external_key": _required(row, "developer_uid"),
            "purchaser_external_key": _required(row, "cg_uid")})


def map_logistics_channel(row: dict[str, Any]) -> EntityInput:
    enabled = _integer(row, "enabled")
    provider = row.get("provider")
    if enabled not in {0, 1} or not isinstance(provider, dict):
        raise ValueError("schema.logistics_channel")
    return EntityInput(entity_type="logistics_channel", external_key=_required(row, "id"),
        name=_required(row, "channel_name"), status="active" if enabled else "inactive",
        attributes={"provider_external_key": _required(provider, "id"),
                    "method_external_key": _required(row, "method_id")})


def map_source_user(row: dict[str, Any]) -> EntityInput:
    user_id = _integer(row, "uid")
    status, master = _integer(row, "status"), _integer(row, "is_master")
    if user_id <= 0 or status not in {0, 1} or master not in {0, 1}:
        raise ValueError("schema.source_user_status")
    return EntityInput(entity_type="source_user", external_key=str(user_id),
        name=_required(row, "realname"), status="active" if status else "inactive",
        attributes={"is_master": bool(master)})


def map_warehouse(row: dict[str, Any]) -> EntityInput:
    kind, deleted = _integer(row, "type"), _integer(row, "is_delete")
    if kind not in {1, 3, 4, 6} or deleted not in {0, 1}:
        raise ValueError("schema.warehouse_status")
    return EntityInput(entity_type="warehouse", external_key=_required(row, "wid"),
                       name=_required(row, "name"), status="inactive" if deleted else "active",
                       attributes={"warehouse_type": kind,
                                   "country_code": str(row.get("country_code") or "")})


def map_shop(row: dict[str, Any]) -> EntityInput:
    states = {0: "inactive", 1: "active", 2: "authorization_error", 3: "suspended"}
    status = states.get(_integer(row, "status"))
    if status is None:
        raise ValueError("schema.shop_status")
    return EntityInput(entity_type="store", external_key=_required(row, "sid"),
                       name=_required(row, "name"), status=status,
                       attributes={key: row[key] for key in ("mid", "country", "marketplace_id")
                                   if key in row})


def map_multiplatform_shop(row: dict[str, Any]) -> EntityInput:
    key = _required(row, "store_id")
    sync, authorized = _integer(row, "is_sync"), _integer(row, "status")
    if sync not in {0, 1} or authorized not in {0, 1}:
        raise ValueError("schema.shop_status")
    currency = _nullable_text(row, "currency")
    return EntityInput(entity_type="store", external_key=f"multiplatform:{key}",
        name=_required(row, "store_name"),
        status="authorization_error" if not authorized else "active" if sync else "inactive",
        attributes={"source_store_id": key, "amazon_sid": str(row.get("sid") or ""),
                    "currency_code": currency,
                    "quality_flags": [] if currency else ["currency_pending"],
                    "platform_code": _integer(row, "platform_code"),
                    "platform_name": _required(row, "platform_name")})


def map_concept_shop(row: dict[str, Any]) -> EntityInput:
    state = _integer(row, "status")
    if state not in {1, 2}:
        raise ValueError("schema.concept_status")
    return EntityInput(entity_type="concept_store", external_key=_required(row, "id"),
        name=_required(row, "name"), status="active" if state == 1 else "inactive",
        requires_assignment=False, attributes={key: row[key] for key in (
            "mid", "seller_id", "seller_account_name", "seller_account_id", "region", "country")
            if key in row})


def map_marketplace(row: dict[str, Any]) -> EntityInput:
    return EntityInput(entity_type="marketplace", external_key=_required(row, "marketplace_id"),
        name=_required(row, "country"), status="active", requires_assignment=False,
        attributes={"mid": _required(row, "mid"), "code": _required(row, "code"),
                    "region": _required(row, "region"),
                    "aws_region": _nullable_text(row, "aws_region")})


def map_subdivision(row: dict[str, Any], *, multiplatform: bool = False) -> EntityInput:
    country = _required(row, "countryCode" if multiplatform else "country_code")
    name = _required(row, "stateOrProvinceName" if multiplatform else "state_or_province_name")
    code = _required(row, "code")
    key = hashlib.sha256(json.dumps([multiplatform, country, name, code],
                                    ensure_ascii=False).encode()).hexdigest()
    return EntityInput(entity_type="country_subdivision", external_key=key, name=name,
        status="active", requires_assignment=False,
        attributes={"country_code": country, "code": code,
                    "source_platform": "multiplatform" if multiplatform else "amazon"})


def map_product(row: dict[str, Any]) -> EntityInput:
    timestamp = _integer(row, "update_time")
    return EntityInput(
        entity_type="product", external_key=_required(row, "id"),
        name=_required(row, "product_name"),
        status="active" if _integer(row, "open_status") == 1 else "inactive",
        attributes={"sku": _required(row, "sku"),
                    **{key: row[key] for key in ("cid", "bid", "spu") if key in row}},
        source_updated_at=datetime.fromtimestamp(timestamp, UTC),
    )


def map_brand(row: dict[str, Any]) -> EntityInput:
    return EntityInput(entity_type="brand", external_key=_required(row, "bid"),
        name=_required(row, "title"), status="present", requires_assignment=False,
        attributes={"brand_code": str(row.get("brand_code") or "")})


def map_category(row: dict[str, Any]) -> EntityInput:
    parent = _integer(row, "parent_cid")
    if parent < 0:
        raise ValueError("schema.parent_category")
    return EntityInput(entity_type="product_category", external_key=_required(row, "cid"),
        name=_required(row, "title"), status="present", requires_assignment=False,
        attributes={"parent_external_key": str(parent) if parent else None,
                    "category_code": str(row.get("category_code") or "")})


def map_supplier(row: dict[str, Any]) -> EntityInput:
    deleted = _integer(row, "is_delete")
    if deleted not in {0, 1}:
        raise ValueError("schema.supplier_deleted")
    return EntityInput(entity_type="supplier", external_key=_required(row, "supplier_id"),
        name=_required(row, "supplier_name"), status="inactive" if deleted else "present",
        attributes={"supplier_code": str(row.get("supplier_code") or ""),
                    "provider_status": _integer(row, "status"),
                    "provider_status_text": str(row.get("status_text") or "")})


def map_head_logistics_provider(row: dict[str, Any]) -> EntityInput:
    enabled, authorized = _integer(row, "enabled"), _integer(row, "status")
    api, payment, kind = (_integer(row, field)
                          for field in ("isAuth", "payMethod", "logisticsType"))
    if (enabled not in {0, 1} or authorized not in {0, 1} or api not in {0, 1}
            or payment not in {1, 2} or kind not in {0, 1, 2, 3, 4}):
        raise ValueError("schema.logistics_status")
    return EntityInput(entity_type="logistics_provider", external_key=_required(row, "providerId"),
        name=_required(row, "name"), status="active" if enabled else "inactive",
        attributes={"code": str(row.get("code") or ""), "authorization_status": authorized,
                    "api_integration": api, "payment_method": payment, "logistics_type": kind})


def map_order(row: dict[str, Any]) -> OrderInput:
    currency = str(row.get("order_total_currency_code") or "").upper() or None
    if currency is not None and (len(currency) != 3 or not currency.isalpha()):
        raise ValueError("schema.currency")
    raw_amount = row.get("order_total_amount")
    try:
        amount = Decimal(str(raw_amount)) if raw_amount not in (None, "") else None
    except InvalidOperation:
        raise ValueError("schema.amount") from None
    if amount is not None and not amount.is_finite():
        raise ValueError("schema.amount")
    local = _required(row, "purchase_date_local")
    try:
        business_date = datetime.fromisoformat(local).date()
    except ValueError:
        raise ValueError("schema.local_time") from None
    lines = row.get("item_list")
    if not isinstance(lines, list) or any(not isinstance(item, dict) for item in lines):
        raise ValueError("schema.order_lines")
    return OrderInput(
        external_key=_required(row, "amazon_order_id"),
        store_external_key=_required(row, "sid"), status=_required(row, "order_status"),
        amount=amount, currency_code=currency,
        ordered_at=_utc(_required(row, "purchase_date_local_utc")),
        source_local_time=local, business_date=business_date,
        source_updated_at=_utc(_required(row, "last_update_date_utc")),
        fulfillment_channel=row.get("fulfillment_channel") or None,
        lines=[OrderLineInput(sku=_required(item, "seller_sku"),
                              local_sku=item.get("local_sku") or None,
                              quantity=_integer(item, "quantity_ordered")) for item in lines],
    )


def map_stock(row: dict[str, Any]) -> StockInput:
    warehouse, product = _required(row, "wid"), _required(row, "product_id")
    identity = [warehouse, product, str(row.get("seller_id") or "0"), str(row.get("fnsku") or "")]
    quantities = {name: _integer(row, field) for name, field in {
        "total": "product_total", "available": "product_valid_num", "defective": "product_bad_num",
        "inspecting": "product_qc_num", "reserved": "product_lock_num",
    }.items()}
    if quantities["total"] != sum(quantities[key] for key in
                                   ("available", "defective", "inspecting", "reserved")):
        raise ValueError("quality.inventory_balance")
    return StockInput(
        external_key=hashlib.sha256(json.dumps(identity).encode()).hexdigest(),
        warehouse_external_key=warehouse, product_external_key=product,
        sku=_required(row, "sku"), store_external_key=identity[2] if identity[2] != "0" else None,
        in_transit=_integer(row, "product_onway") if row.get("product_onway") is not None else None,
        **quantities,
    )
