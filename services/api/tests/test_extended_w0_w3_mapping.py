from dataclasses import replace
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from zhixing_connectors.catalog import RESOURCE_CATALOG, can_project_to_core

from zhixing_api.data_models import (
    Base,
    BusinessEntity,
    BusinessUnit,
    CanonicalEntityOrigin,
    CanonicalOperationalFact,
    ExternalSystem,
    SourceBinding,
)
from zhixing_api.database import Database
from zhixing_api.ingestion.operational_facts import (
    map_ad_campaign,
    map_customer_review,
    map_exchange_rate,
    map_fbm_order,
    map_finance_fee,
    map_product_attribute,
    map_purchase_order,
    map_source_order,
    map_warehouse_bin,
)
from zhixing_api.ingestion.persistence import _object_key, _persist_row
from zhixing_api.ingestion.queries import canonical_page
from zhixing_api.scope_context import ScopeContext


def test_remaining_w0_w3_catalog_contracts_are_projectable() -> None:
    items = [item for item in RESOURCE_CATALOG if item.wave in {"W0", "W1", "W2", "W3"}]
    assert items
    assert all(item.schema_status == "confirmed" and can_project_to_core(item) for item in items)


def test_reviewed_w4_w8_resources_have_strict_operational_mappers() -> None:
    reviewed = {"purchases", "advertising", "finance", "customer_service", "source_reports"}
    specs = {item.key: item for item in RESOURCE_CATALOG if item.key in reviewed}
    assert specs.keys() == reviewed
    assert all(item.schema_status == "confirmed" and can_project_to_core(item)
               for item in specs.values())
    assert next(item for item in RESOURCE_CATALOG
                if item.key == "report_export_status").schema_status == "schema_pending"


def test_reference_mappers_keep_only_confirmed_fields() -> None:
    rate = map_exchange_rate({"date": "2026-09", "code": "usd", "name": "Synthetic",
                              "rate_org": "7.125", "my_rate": ""})
    assert rate.external_key == "2026-09:USD" and str(rate.quantity) == "7.125"
    assert rate.attributes["value_kind"] == "provider_rate"
    assert rate.quality_flags == ["rate_direction_pending", "base_currency_pending"]
    attribute = map_product_attribute({"pa_id": 7, "attr_name": "Synthetic size",
        "item_list": [{"pai_id": 8, "attr_value": "Synthetic value",
                       "private_note": "must not persist"}]})
    assert attribute.attributes == {"values": [{"external_key": "8",
                                                 "value": "Synthetic value"}]}
    warehouse_bin, warehouse = map_warehouse_bin({"id": 9, "wid": 22,
        "storage_bin": "SYNTHETIC-BIN", "whb_status": 2, "type": 5,
        "sku_fnsku": [{"SKU": "not persisted"}]})
    assert warehouse == "22" and warehouse_bin.status == "active"
    with pytest.raises(ValueError):
        map_exchange_rate({"date": "2026-09", "code": "USD", "name": "Synthetic"})


def test_fbm_identity_and_conflict_key_include_request_store() -> None:
    row = {"order_number": "SAME", "status": "pending",
           "purchase_time": "2026-09-09 12:00:00", "wid": 22}
    assert map_fbm_order(row, {"sid": "11"}).external_key != map_fbm_order(
        row, {"sid": "12"}).external_key
    assert _object_key(row, 0, "raw", {"sid": "11"}) != _object_key(
        row, 0, "raw", {"sid": "12"})


def test_w4_w8_mappers_keep_business_fields_and_exclude_customer_text() -> None:
    purchase = map_purchase_order({"order_sn": "PO-1", "status": 9, "wid": 22,
        "update_time": "2026-09-09 10:00:00", "total_price": "12.125",
        "purchase_currency": "CNY", "quantity_total": 3, "supplier_id": 8,
        "item_list": [{"id": 1, "wid": 22, "product_id": 33, "sku": "SKU-33",
                       "quantity_real": 3, "price": "4.041666666667"}]})
    assert purchase.fact_type == "purchase_order" and purchase.warehouse_external_key == "22"
    assert str(purchase.amount) == "12.125" and purchase.attributes["item_count"] == 1
    campaign = map_ad_campaign({"campaign_id": 2, "state": "enabled",
        "name": "Synthetic campaign", "campaign_type": "sponsoredProducts",
        "daily_budget": "5.125", "last_updated_date": 1789000000000}, {"sid": 11})
    assert campaign.store_external_key == "11" and str(campaign.amount) == "5.125"
    fee = map_finance_fee({"id": "3", "status_order_id": 3, "date": "2026-09-09",
        "fee": "-1.125", "currency_code": "USD", "dimension_id": 3,
        "details": [{"fof_id": "4", "store_infos": [{"id": 11, "name": "Synthetic"}]}]},
        {"sids": [11]})
    assert fee.store_external_key == "11" and str(fee.amount) == "-1.125"
    review = map_customer_review({"review_id": "R-4", "status": 0,
        "review_date": "2026-09-08", "update_time": "2026-09-09 11:00:00",
        "asin": "ASIN-4", "last_star": 5, "last_title": "must not persist",
        "last_content": "must not persist", "buyer_email": ["private@example.invalid"],
        "author": "must not persist"}, {"sids": "11"})
    assert review.store_external_key == "11"
    assert not {"last_title", "last_content", "buyer_email", "author"} & review.attributes.keys()
    source_order = map_source_order({"amazon_order_id": "A-5", "sid": 11,
        "order_status": "Shipped", "purchase_date": "2026-09-09T12:00:00+00:00",
        "sku": "MSKU-5", "asin": "ASIN-5", "pid": 33, "quantity": 2,
        "currency": "USD", "item_price": "7.125"}, {"sid": 11})
    assert source_order.product_external_key == "33"
    assert source_order.quality_flags == ["order_total_not_derived"]


def test_operational_fact_mapping_is_scoped_idempotent_and_preserves_lineage() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 10, tzinfo=UTC)
    with Session(engine) as session:
        session.add(BusinessUnit(id="project", enterprise_id="legal", unit_key="project",
            name="Synthetic project", unit_type="project", status="active",
            created_at=now, updated_at=now))
        source = ExternalSystem(id="source", enterprise_id="legal", business_unit_id="project",
            system_key="source", name="Synthetic", system_type="lingxing",
            base_url="https://openapi.lingxing.com", status="configured")
        session.add(source)
        for kind, external, canonical in (
            ("store", "11", "store-key"), ("warehouse", "22", "warehouse-key"),
            ("product", "33", "product-key"),
        ):
            session.add(BusinessEntity(id=canonical, enterprise_id="legal", entity_type=kind,
                canonical_key=canonical, display_name=f"Synthetic {kind}", status="active",
                attributes={}, updated_at=now))
            session.add(SourceBinding(id=f"binding-{kind}", enterprise_id="legal",
                business_unit_id="project", source_system_id="source",
                external_key=f"{kind}:{external}", canonical_type=kind,
                canonical_id=canonical, mapping_version="test", status="approved",
                created_at=now, updated_at=now))
        session.flush()
        scope = {"business_unit_ids": ["project"], "store_ids": ["store-key"],
                 "warehouse_ids": ["warehouse-key"]}
        rows = {
            "monthly_exchange_rates": ({"date": "2026-09", "code": "USD",
                "name": "Synthetic currency", "rate_org": "7.125", "my_rate": ""}, {}),
            "fbm_orders": ({"order_number": "FBM-1", "status": 2,
                "purchase_time": "2026-09-09 12:00:00", "wid": 22,
                "country_code": "US", "customer_comment": "must not persist"}, {"sid": "11"}),
            "fba_shipments": ({"id": 2, "shipment_sn": "FBA-2", "status": 1,
                "update_time": "2026-09-09 13:00:00",
                "relate_list": [{"sid": 11, "wid": 22, "quantity_shipped": 3}]}, {}),
            "inbound_orders": ({"order_sn": "IB-3", "status": 40, "wid": 22,
                "increment_time": "2026-09-09 14:00:00", "order_amount": "4.125",
                "currency": "USD", "item_list": [{"product_total": 2}]}, {}),
            "outbound_orders": ({"order_sn": "OB-4", "status": 40, "wid": 22,
                "increment_time": "2026-09-09 15:00:00", "order_amount": "5.125",
                "currency": "USD", "item_list": [{"product_total": 1}]}, {}),
            "inventory_statements": ({"statement_id": 5, "wid": 22, "product_id": 33,
                "sku": "SKU-33", "opt_time": "2026-09-09 16:00:00",
                "stock_cost": "6.125", "product_total": -1, "type": 42,
                "sub_type": 4201, "order_sn": "MOV-5"}, {}),
            "fba_inventory": ({"sid": 11, "seller_sku": "MSKU-6", "fnsku": "FNSKU-6",
                "asin": "ASIN-6", "total": 7, "available_total": 5,
                "afn_reserved_quantity": 2}, {}),
            "purchases": ({"order_sn": "PO-7", "status": 9, "wid": 22,
                "update_time": "2026-09-09 17:00:00", "total_price": "8.125",
                "purchase_currency": "CNY", "quantity_total": 2, "supplier_id": 8,
                "item_list": [{"id": 1, "wid": 22, "product_id": 33,
                               "sku": "SKU-33", "quantity_real": 2}]}, {}),
            "advertising": ({"campaign_id": 8, "state": "enabled", "name": "Synthetic",
                "campaign_type": "sponsoredProducts", "daily_budget": "9.125",
                "last_updated_date": 1789000000000}, {"sid": 11}),
            "finance": ({"id": "9", "status_order_id": 3, "date": "2026-09-09",
                "fee": "-2.125", "currency_code": "USD", "dimension_id": 3,
                "details": [{"fof_id": "9-1", "store_infos": [{"id": 11}]}]},
                {"sids": [11]}),
            "customer_service": ({"review_id": "R-10", "status": 0,
                "review_date": "2026-09-09", "update_time": "2026-09-09 18:00:00",
                "asin": "ASIN-10", "last_star": 4, "last_content": "private"},
                {"sids": "11"}),
            "source_reports": ({"amazon_order_id": "A-11", "sid": 11,
                "order_status": "Shipped", "purchase_date": "2026-09-09T19:00:00+00:00",
                "sku": "MSKU-11", "asin": "ASIN-11", "pid": 33, "quantity": 1,
                "currency": "USD", "item_price": "10.125"}, {"sid": 11}),
        }
        for index, (resource, (row, request)) in enumerate(rows.items()):
            assert _persist_row(session, source, resource, f"raw-{index}", row, now,
                                scope, request) == "accepted"
        assert _persist_row(session, source, "fbm_orders", "raw-repeat",
            rows["fbm_orders"][0], now, scope, {"sid": "11"}) == "accepted"
        session.commit()
        facts = list(session.scalars(select(CanonicalOperationalFact)))
        assert len(facts) == 12
        exchange_rate = next(item for item in facts if item.fact_type == "exchange_rate")
        assert exchange_rate.business_unit_id is None
        assert all(item.raw_manifest_id.startswith("raw-") for item in facts)
        assert all(item.business_unit_id == "project" for item in facts
                   if item.fact_type != "exchange_rate")
        assert not any("customer_comment" in item.attributes for item in facts)

        bin_result = _persist_row(session, source, "warehouse_bins", "raw-bin",
            {"id": 9, "wid": 22, "storage_bin": "SYNTHETIC-BIN",
             "whb_status": 2, "type": 5}, now, scope)
        assert bin_result == "accepted"
        bin_origin = session.scalar(select(CanonicalEntityOrigin).where(
            CanonicalEntityOrigin.resource_key == "warehouse_bins"))
        assert bin_origin.business_unit_id == "project" and bin_origin.status == "assigned"
    database = Database.from_engine(engine)
    scope = ScopeContext(group_id="group", group_name="Synthetic", enterprise_id="legal",
        enterprise_name="Synthetic", allowed_enterprise_ids=("legal",),
        selected_enterprise_ids=("legal",), business_unit_ids=("project",),
        store_ids=("store-key",), warehouse_ids=("warehouse-key",),
        timezone="UTC", scope_version="test")
    page = canonical_page(database, scope, "operational")
    assert page.total == 12 and all(item.raw_manifest_id.startswith("raw-")
                                   for item in page.items)
    hidden = canonical_page(database, replace(scope, store_ids=(), warehouse_ids=()),
                            "operational")
    assert hidden.total == 1
    database.dispose()
