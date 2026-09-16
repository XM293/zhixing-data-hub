from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest


def synthetic_fulfillment():
    return {"wo_id": 71, "wo_number": "SYNTHETIC-WO", "sid": 91, "wid": 92,
        "status": 3, "logistics_status": 5, "order_number": "SYNTHETIC-SYSTEM-ORDER",
        "platform_order_no": ["SYNTHETIC-AMAZON-ORDER"],
        "create_at": "2026-09-09 10:00:00", "update_at": "2026-09-09 11:00:00",
        "delivered_at": "2026-09-09 10:30:00",
        "logistics_freight": "1.125", "logistics_freight_currency_code": "KWD",
        "order_origin_amount": "999.99", "order_currency_code": "USD",
        "consignee_phone": "SYNTHETIC-NOT-A-PHONE",
        "product_info": [{"wod_id": 72, "product_id": 93, "sku": "SYNTHETIC-SKU",
                          "count": 2, "bundle_type": 0}]}


def test_fulfillment_preserves_identity_precision_and_unknown_source_timezone():
    from zhixing_api.ingestion.fulfillments import map_fulfillment

    mapped = map_fulfillment(synthetic_fulfillment())
    assert mapped.external_key == "71" and mapped.shipment_number == "SYNTHETIC-WO"
    assert mapped.status == "dispatched" and mapped.freight_amount == Decimal("1.125")
    assert mapped.freight_currency_code == "KWD"
    assert mapped.source_updated_at is None and mapped.source_timezone is None
    assert mapped.business_date.isoformat() == "2026-09-09"
    assert "source_timezone_pending" in mapped.quality_flags
    assert mapped.lines[0].external_key == "72" and mapped.lines[0].quantity == 2
    assert not ({"order_origin_amount", "consignee_phone"} & mapped.model_dump().keys())
    pending = map_fulfillment({**synthetic_fulfillment(), "logistics_freight_currency_code": "$"})
    assert pending.freight_currency_code is None
    assert "freight_currency_pending" in pending.quality_flags


@pytest.mark.parametrize("change", [
    {"status": 99}, {"logistics_status": 99}, {"wo_id": True}, {"sid": 0},
    {"create_at": "not-a-date"}, {"logistics_freight": "NaN"},
    {"update_at": "2026-09-09T11:00:00Z"}, {"product_info": None},
    {"wo_number": "x" * 201},
])
def test_fulfillment_rejects_unconfirmed_schema_before_writing(change):
    from zhixing_api.ingestion.fulfillments import map_fulfillment

    with pytest.raises(ValueError):
        map_fulfillment({**synthetic_fulfillment(), **change})


def test_fulfillment_line_identity_and_bundle_relationship_are_not_quantity_totals():
    from zhixing_api.ingestion.fulfillments import map_fulfillment

    row = synthetic_fulfillment()
    parent = {**row["product_info"][0], "bundle_type": 1}
    child = {**parent, "wod_id": 73, "bundle_type": 2, "bundle_wod_id": 72, "count": 3}
    mapped = map_fulfillment({**row, "product_info": [parent, child]})
    assert mapped.lines[1].parent_external_key == "72"
    assert [line.quantity for line in mapped.lines] == [2, 3]
    for items in ([parent, deepcopy(parent)], [{**child, "bundle_wod_id": 0}],
                  [{**parent, "count": -1}]):
        with pytest.raises(ValueError):
            map_fulfillment({**row, "product_info": items})


def test_fulfillment_public_contract_matches_serialized_read_model():
    import json

    from zhixing_api.ingestion.read_models import FulfillmentView

    root = Path(__file__).resolve().parents[3]
    contract = json.loads((root / "contracts/data/canonical-fulfillment.schema.json")
                          .read_text(encoding="utf-8"))
    assert contract == FulfillmentView.model_json_schema(mode="serialization")
