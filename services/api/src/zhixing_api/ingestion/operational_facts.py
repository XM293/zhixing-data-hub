"""Strict source mappings for facts that do not fit legacy commerce tables."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .mapping import EntityInput, _integer, _nullable_text, _required


class OperationalFactInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    fact_type: str
    external_key: str
    status: str
    store_external_key: str | None = None
    warehouse_external_key: str | None = None
    product_external_key: str | None = None
    source_local_time: str | None = None
    business_date: date | None = None
    amount: Decimal | None = None
    currency_code: str | None = None
    quantity: Decimal | None = None
    attributes: dict[str, Any]
    quality_flags: list[str] = Field(default_factory=list)


def _decimal(row: dict[str, Any], key: str) -> Decimal | None:
    value = row.get(key)
    if value in (None, ""):
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(f"schema.decimal:{key}") from None
    if not result.is_finite():
        raise ValueError(f"schema.decimal:{key}")
    return result


def _date_prefix(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError("schema.local_date") from None


def _optional_id(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value in (None, "") or isinstance(value, bool) or isinstance(value, (list, dict)):
        return None
    return str(value)


def _currency(row: dict[str, Any], key: str) -> str | None:
    value = str(row.get(key) or "").upper() or None
    if value is not None and (len(value) != 3 or not value.isalpha()):
        raise ValueError("schema.currency")
    return value


def _single_request_store(request: dict[str, object]) -> str:
    value = request.get("sid", request.get("sids"))
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        values = [part for part in value.split(",") if part]
    else:
        values = [value]
    if len(values) != 1:
        raise ValueError("schema.store_scope_ambiguous")
    item = values[0]
    if isinstance(item, bool) or item in (None, "") or not str(item).isdigit():
        raise ValueError("schema.store_scope_invalid")
    return str(int(str(item)))


def _epoch_millis(value: object) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("schema.epoch_millis")
    try:
        milliseconds = int(str(value))
        return datetime.fromtimestamp(milliseconds / 1000, UTC).isoformat()
    except (ValueError, OverflowError, OSError):
        raise ValueError("schema.epoch_millis") from None


def map_exchange_rate(row: dict[str, Any]) -> OperationalFactInput:
    month = _required(row, "date")
    try:
        business_date = date.fromisoformat(f"{month}-01" if len(month) == 7 else month[:10])
    except ValueError:
        raise ValueError("schema.rate_month") from None
    code = _required(row, "code").upper()
    if len(code) != 3 or not code.isalpha():
        raise ValueError("schema.currency")
    provider_rate = _decimal(row, "rate_org")
    configured_rate = _decimal(row, "my_rate")
    if provider_rate is None and configured_rate is None:
        raise ValueError("schema.rate_missing")
    return OperationalFactInput(fact_type="exchange_rate", external_key=f"{month}:{code}",
        status="present", business_date=business_date, currency_code=code,
        quantity=configured_rate if configured_rate is not None else provider_rate,
        attributes={"currency_name": _required(row, "name"),
                    "provider_rate": str(provider_rate) if provider_rate is not None else None,
                    "configured_rate": (str(configured_rate)
                                        if configured_rate is not None else None),
                    "value_kind": ("configured_rate" if configured_rate is not None
                                   else "provider_rate")},
        quality_flags=["rate_direction_pending", "base_currency_pending"])


def map_product_attribute(row: dict[str, Any]) -> EntityInput:
    identity = _required(row, "pa_id")
    values = row.get("item_list")
    if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
        raise ValueError("schema.attribute_values")
    normalized = [{"external_key": _required(item, "pai_id"),
                   "value": _required(item, "attr_value")} for item in values]
    return EntityInput(entity_type="product_attribute", external_key=identity,
        name=_required(row, "attr_name"), status="present", requires_assignment=False,
        attributes={"values": normalized})


def map_warehouse_bin(row: dict[str, Any]) -> tuple[EntityInput, str]:
    state, kind = _integer(row, "whb_status"), _integer(row, "type")
    if state not in {1, 2} or kind not in {5, 6}:
        raise ValueError("schema.warehouse_bin_status")
    warehouse = _required(row, "wid")
    return (EntityInput(entity_type="warehouse_bin", external_key=_required(row, "id"),
        name=_required(row, "storage_bin"), status="active" if state == 2 else "inactive",
        requires_assignment=False,
        attributes={"warehouse_external_key": warehouse, "bin_type": kind}), warehouse)


def map_fbm_order(row: dict[str, Any], request: dict[str, object]) -> OperationalFactInput:
    sid = _required(request, "sid")
    if "," in sid:
        raise ValueError("schema.fbm_store_ambiguous")
    local_time = _required(row, "purchase_time")
    return OperationalFactInput(fact_type="fbm_order",
        external_key=json.dumps([sid, _required(row, "order_number")],
                                ensure_ascii=False, separators=(",", ":")),
        status=_required(row, "status"),
        store_external_key=sid, warehouse_external_key=_optional_id(row, "wid"),
        source_local_time=local_time, business_date=_date_prefix(local_time),
        attributes={key: row[key] for key in (
            "order_from", "country_code", "logistics_type_id", "logistics_provider_id")
            if row.get(key) not in (None, "")}, quality_flags=["source_timezone_pending"])


def map_fba_shipment(row: dict[str, Any]) -> OperationalFactInput:
    relations = row.get("relate_list")
    if not isinstance(relations, list) or any(not isinstance(item, dict) for item in relations):
        raise ValueError("schema.shipment_relations")
    stores = {_required(item, "sid") for item in relations}
    warehouses = {_required(item, "wid") for item in relations}
    if len(stores) != 1 or len(warehouses) != 1:
        raise ValueError("schema.shipment_scope_ambiguous")
    local_time = _nullable_text(row, "update_time") or _nullable_text(row, "gmt_create")
    return OperationalFactInput(fact_type="fba_shipment",
        external_key=_required(row, "id"), status=_required(row, "status"),
        store_external_key=stores.pop(), warehouse_external_key=warehouses.pop(),
        source_local_time=local_time, business_date=_date_prefix(local_time),
        quantity=sum(((_decimal(item, "quantity_shipped") or Decimal(0))
                      for item in relations), start=Decimal(0)),
        attributes={"shipment_number": _required(row, "shipment_sn"),
                    "item_count": len(relations)}, quality_flags=["source_timezone_pending"])


def map_inventory_document(row: dict[str, Any], direction: str) -> OperationalFactInput:
    if direction not in {"inbound", "outbound"}:
        raise ValueError("schema.inventory_direction")
    items = row.get("item_list")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("schema.inventory_document_items")
    local_time = (_nullable_text(row, "increment_time")
                  or _nullable_text(row, f"{direction}_time")
                  or _nullable_text(row, "create_time"))
    currency = str(row.get("currency") or "").upper() or None
    if currency is not None and (len(currency) != 3 or not currency.isalpha()):
        raise ValueError("schema.currency")
    total = sum(((_decimal(item, "product_total") or Decimal(0)) for item in items),
                start=Decimal(0))
    flags = (["source_timezone_pending"] if local_time else [])
    if _decimal(row, "order_amount") is not None and currency is None:
        flags.append("currency_pending")
    return OperationalFactInput(fact_type=f"{direction}_order",
        external_key=_required(row, "order_sn"), status=_required(row, "status"),
        warehouse_external_key=_required(row, "wid"), source_local_time=local_time,
        business_date=_date_prefix(local_time), amount=_decimal(row, "order_amount"),
        currency_code=currency, quantity=total,
        attributes={"document_type": row.get("type"), "item_count": len(items)},
        quality_flags=flags)


def map_inventory_statement(row: dict[str, Any]) -> OperationalFactInput:
    local_time = _required(row, "opt_time")
    return OperationalFactInput(fact_type="inventory_movement",
        external_key=_required(row, "statement_id"), status="posted",
        warehouse_external_key=_required(row, "wid"),
        product_external_key=_required(row, "product_id"),
        source_local_time=local_time, business_date=_date_prefix(local_time),
        amount=_decimal(row, "stock_cost"), quantity=_decimal(row, "product_total"),
        attributes={"document_number": str(row.get("order_sn") or ""),
                    "movement_type": str(row.get("type") or ""),
                    "movement_subtype": str(row.get("sub_type") or ""),
                    "sku": _required(row, "sku")},
        quality_flags=["currency_pending", "source_timezone_pending"])


def map_fba_inventory(row: dict[str, Any]) -> OperationalFactInput:
    sid, sku = _required(row, "sid"), _required(row, "seller_sku")
    total = _decimal(row, "total")
    if total is None:
        raise ValueError("schema.inventory_total")
    return OperationalFactInput(fact_type="fba_inventory",
        external_key=json.dumps([sid, sku, str(row.get("fnsku") or "")],
                                  ensure_ascii=False, separators=(",", ":")),
        status="observed", store_external_key=sid, quantity=total,
        attributes={"seller_sku": sku, "fnsku": str(row.get("fnsku") or ""),
                    "asin": str(row.get("asin") or ""),
                    "available": str(_decimal(row, "available_total") or Decimal(0)),
                    "reserved": str(_decimal(row, "afn_reserved_quantity") or Decimal(0))},
        quality_flags=[])


def map_purchase_order(row: dict[str, Any]) -> OperationalFactInput:
    items = row.get("item_list")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("schema.purchase_items")
    local_time = _required(row, "update_time")
    normalized_items = [
        {
            key: (str(_decimal(item, key)) if key in {"price", "amount"}
                  and item.get(key) not in (None, "") else item[key])
            for key in (
                "id", "wid", "product_id", "sku", "fnsku", "sid", "price", "amount",
                "quantity_plan", "quantity_real", "quantity_entry", "quantity_receive",
                "quantity_return", "quantity_exchange", "is_delete",
            )
            if item.get(key) not in (None, "")
        }
        for item in items
    ]
    return OperationalFactInput(
        fact_type="purchase_order",
        external_key=_required(row, "order_sn"),
        status=_required(row, "status"),
        warehouse_external_key=_required(row, "wid"),
        source_local_time=local_time,
        business_date=_date_prefix(local_time),
        amount=_decimal(row, "total_price"),
        currency_code=_currency(row, "purchase_currency"),
        quantity=_decimal(row, "quantity_total"),
        attributes={
            "custom_order_number": str(row.get("custom_order_sn") or ""),
            "supplier_external_key": str(row.get("supplier_id") or ""),
            "shipping_status": row.get("status_shipped"),
            "payment_status": row.get("pay_status"),
            "purchase_type": row.get("purchase_type"),
            "item_count": len(items),
            "items": normalized_items,
        },
        quality_flags=["source_timezone_pending"],
    )


def map_ad_campaign(row: dict[str, Any], request: dict[str, object]) -> OperationalFactInput:
    sid = _single_request_store(request)
    updated = _epoch_millis(row.get("last_updated_date"))
    start_date = _nullable_text(row, "start_date")
    return OperationalFactInput(
        fact_type="advertising_campaign",
        external_key=json.dumps(
            [sid, _required(row, "campaign_id")], ensure_ascii=False, separators=(",", ":")
        ),
        status=_required(row, "state"),
        store_external_key=sid,
        source_local_time=updated,
        business_date=_date_prefix(updated or start_date),
        amount=_decimal(row, "daily_budget"),
        attributes={
            key: row[key]
            for key in (
                "name", "campaign_type", "targeting_type", "profile_id", "portfolio_id",
                "start_date", "end_date", "serving_status",
            )
            if row.get(key) not in (None, "")
        },
        quality_flags=["budget_currency_pending"],
    )


def map_finance_fee(row: dict[str, Any], request: dict[str, object]) -> OperationalFactInput:
    sid = _single_request_store(request)
    details = row.get("details")
    if not isinstance(details, list) or any(not isinstance(item, dict) for item in details):
        raise ValueError("schema.finance_fee_details")
    observed_store_ids: set[str] = set()
    normalized_details = []
    for item in details:
        stores = item.get("store_infos")
        if stores is not None and (
            not isinstance(stores, list) or any(not isinstance(store, dict) for store in stores)
        ):
            raise ValueError("schema.finance_fee_stores")
        store_ids = [
            _required(store, "id") for store in stores or []
        ]
        observed_store_ids.update(store_ids)
        normalized_details.append({
            "external_key": _required(item, "fof_id"),
            "dimension_id": item.get("dimension_id"),
            "dimension_value": str(item.get("dimension_value") or ""),
            "amount": (str(_decimal(item, "fee"))
                       if item.get("fee") not in (None, "") else None),
            "store_external_keys": store_ids,
        })
    if observed_store_ids and observed_store_ids != {sid}:
        raise ValueError("schema.finance_fee_scope")
    local_time = _nullable_text(row, "create_time") or _required(row, "date")
    return OperationalFactInput(
        fact_type="other_fee",
        external_key=_required(row, "id"),
        status=_required(row, "status_order_id"),
        store_external_key=sid,
        source_local_time=local_time,
        business_date=_date_prefix(_required(row, "date")),
        amount=_decimal(row, "fee"),
        currency_code=_currency(row, "currency_code"),
        attributes={
            "document_number": str(row.get("number") or ""),
            "dimension_id": row.get("dimension_id"),
            "allocation_status": str(row.get("allocation_status") or ""),
            "fee_type_external_key": str(row.get("other_fee_type_id") or ""),
            "details": normalized_details,
        },
        quality_flags=["source_timezone_pending"],
    )


def map_customer_review(row: dict[str, Any], request: dict[str, object]) -> OperationalFactInput:
    sid = _single_request_store(request)
    local_time = _nullable_text(row, "update_time") or _required(row, "review_date")
    return OperationalFactInput(
        fact_type="customer_review",
        external_key=json.dumps(
            [sid, _required(row, "review_id")], ensure_ascii=False, separators=(",", ":")
        ),
        status=_required(row, "status"),
        store_external_key=sid,
        source_local_time=local_time,
        business_date=_date_prefix(_required(row, "review_date")),
        quantity=_decimal(row, "last_star"),
        attributes={
            "asin": str(row.get("asin") or ""),
            "seller_skus": (
                row.get("seller_sku") if isinstance(row.get("seller_sku"), list) else []
            ),
            "parent_asins": (
                row.get("parent_asin") if isinstance(row.get("parent_asin"), list) else []
            ),
            "review_likes": row.get("review_likes"),
            "review_modified_status": row.get("review_modified_status"),
            "marketplace": str(row.get("marketplace") or ""),
            "is_verified_purchase": row.get("is_vp"),
            "is_early_reviewer": row.get("is_er"),
            "is_vine": row.get("is_vine"),
        },
        quality_flags=["source_timezone_pending", "customer_text_raw_only"],
    )


def map_source_order(row: dict[str, Any], request: dict[str, object]) -> OperationalFactInput:
    sid = _single_request_store(request)
    if _required(row, "sid") != sid:
        raise ValueError("schema.source_order_scope")
    local_time = _required(row, "purchase_date")
    product = _optional_id(row, "pid")
    return OperationalFactInput(
        fact_type="amazon_order_line",
        external_key=json.dumps(
            [sid, _required(row, "amazon_order_id"), _required(row, "sku"),
             str(row.get("asin") or ""), str(product or "")],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        status=_required(row, "order_status"),
        store_external_key=sid,
        product_external_key=product,
        source_local_time=local_time,
        business_date=_date_prefix(
            _nullable_text(row, "purchase_date_local") or local_time
        ),
        amount=_decimal(row, "item_price"),
        currency_code=_currency(row, "currency"),
        quantity=_decimal(row, "quantity"),
        attributes={
            key: (str(row[key]) if key not in {"item_tax", "shipping_price", "shipping_tax",
                                               "gift_wrap_price", "gift_wrap_tax",
                                               "item_promotion_discount",
                                               "ship_promotion_discount"}
                  else str(_decimal(row, key)) if row.get(key) not in (None, "") else "")
            for key in (
                "merchant_order_id", "fulfillment_channel", "sales_channel", "sku", "asin",
                "local_sku", "item_status", "item_tax", "shipping_price", "shipping_tax",
                "gift_wrap_price", "gift_wrap_tax", "item_promotion_discount",
                "ship_promotion_discount",
            )
            if row.get(key) not in (None, "")
        },
        quality_flags=["order_total_not_derived"],
    )
