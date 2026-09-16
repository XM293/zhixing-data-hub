from datetime import UTC, datetime
from decimal import Decimal

import pytest

from zhixing_api.ingestion.mapping import map_order, map_product, map_shop, map_stock


def test_official_shop_and_product_contracts_use_stable_keys():
    shop = map_shop({"sid": 91, "name": "Synthetic Store", "status": 1})
    assert shop.external_key == "91" and shop.entity_type == "store"
    product = map_product({"id": 71, "sku": "SYN-71", "product_name": "合成柜",
                           "open_status": 1, "update_time": 1788912000})
    assert product.external_key == "71" and product.attributes["sku"] == "SYN-71"
    assert product.source_updated_at.tzinfo is not None


def test_order_total_is_decimal_without_inventing_paid_or_base_amount():
    order = map_order({
        "sid": "91", "amazon_order_id": "SYN-ORDER-1", "order_status": "Shipped",
        "order_total_amount": "123.456", "order_total_currency_code": "KWD",
        "purchase_date_local": "2026-09-08 23:30:00",
        "purchase_date_local_utc": "2026-09-09 06:30:00",
        "last_update_date_utc": "2026-09-09 07:00:00", "fulfillment_channel": "AFN",
        "item_list": [{"seller_sku": "SYN-71", "quantity_ordered": 2}],
    })
    assert order.amount == Decimal("123.456")
    assert order.currency_code == "KWD" and order.business_date.isoformat() == "2026-09-08"
    assert order.ordered_at == datetime(2026, 9, 9, 6, 30, tzinfo=UTC)
    assert order.lines[0].quantity == 2
    assert "paid_amount" not in order.model_dump()


def test_invalid_order_is_rejected_instead_of_generating_missing_fields():
    with pytest.raises(ValueError):
        map_order({"amazon_order_id": "SYN-MISSING-STORE", "order_total_amount": "NaN"})


def test_inventory_checks_actual_balance_and_does_not_invent_cost_currency():
    payload = {"wid": 31, "product_id": 71, "sku": "SYN-71", "seller_id": "0",
               "fnsku": "", "product_total": 12, "product_valid_num": 7,
               "product_bad_num": 1, "product_qc_num": 2, "product_lock_num": 2,
               "product_onway": 3, "stock_cost_total": "999.99"}
    stock = map_stock(payload)
    assert stock.total == 12 and stock.available == 7
    assert "stock_cost_total" not in stock.model_dump()
    with pytest.raises(ValueError, match="balance"):
        map_stock({**payload, "product_total": 15})
def test_warehouse_mapping_preserves_deleted_state_and_does_not_assign_a_project():
    from zhixing_api.ingestion.mapping import map_warehouse

    row = map_warehouse({"wid": 71, "name": "Synthetic warehouse", "type": 3,
                         "is_delete": "1", "country_code": "GB"})
    assert row.entity_type == "warehouse" and row.external_key == "71"
    assert row.status == "inactive" and row.attributes["country_code"] == "GB"
    assert "business_unit_id" not in row.attributes
