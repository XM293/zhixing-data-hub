from datetime import UTC, datetime

import httpx
import pytest

from zhixing_api.connectors.mock_commerce import ConnectorProfile, MockCommerceConnector


@pytest.mark.anyio
async def test_provider_fields_are_mapped_to_canonical_projection() -> None:
    generated_at = datetime.now(UTC).isoformat()
    payloads: dict[str, dict[str, object]] = {
        "/api/v1/profile": {"schema_version": "vendor-7", "generated_at": generated_at},
        "/api/v1/shops": {
            "generated_at": generated_at,
            "items": [
                {
                    "shop_code": "EXT-001",
                    "shop_title": "外部旗舰店",
                    "channel": "tmall",
                    "shop_state": "ACTIVE",
                    "manager_name": "测试经理",
                }
            ],
        },
        "/api/v1/products": {
            "generated_at": generated_at,
            "items": [
                {
                    "product_code": "SPU-001",
                    "product_name": "外部商品",
                    "product_state": "ACTIVE",
                    "brand_name": "测试品牌",
                    "category_name": "测试分类",
                    "owner_team": "商品组",
                }
            ],
        },
        "/api/v1/skus": {
            "generated_at": generated_at,
            "items": [
                {
                    "sku_code": "SKU-001",
                    "sku_name": "外部规格",
                    "product_code": "SPU-001",
                    "warehouse_code": "WH-001",
                    "available_stock": 120,
                    "safety_stock": 40,
                    "sell_state": "ACTIVE",
                }
            ],
        },
        "/api/v1/warehouses": {
            "generated_at": generated_at,
            "items": [
                {
                    "warehouse_code": "WH-001",
                    "warehouse_name": "外部仓",
                    "warehouse_state": "OPERATING",
                    "region_name": "华东",
                    "manager_name": "测试仓管",
                    "capacity_units": 10000,
                }
            ],
        },
        "/api/v1/customers": {
            "generated_at": generated_at,
            "items": [
                {
                    "customer_code": "CUS-001",
                    "customer_name": "外部会员",
                    "member_state": "ACTIVE",
                    "member_segment": "成长",
                    "province_name": "浙江",
                    "total_order_count": 3,
                }
            ],
        },
        "/api/v1/orders/recent": {
            "generated_at": generated_at,
            "items": [
                {
                    "order_code": "ORD-001",
                    "shop_code": "EXT-001",
                    "customer_code": "CUS-001",
                    "paid_amount_fen": 12000,
                    "order_state": "PAID",
                }
            ],
        },
        "/api/v1/orders/summary": {
            "business_date": "2026-08-25",
            "generated_at": generated_at,
            "paid_order_count": 120,
            "paid_gmv_fen": 123456,
            "refund_rate_bps": 515,
            "gmv_change_bps": 800,
            "order_change_bps": 600,
            "refund_change_bps": 100,
        },
        "/api/v1/inventory/summary": {
            "business_date": "2026-08-25",
            "generated_at": generated_at,
            "low_stock_sku_count": 9,
        },
        "/api/v1/ads/summary": {
            "business_date": "2026-08-25",
            "generated_at": generated_at,
            "roi_x100": 318,
            "roi_change_bps": -200,
        },
        "/api/v1/crm/summary": {
            "business_date": "2026-08-25",
            "generated_at": generated_at,
            "active_member_count": 8800,
            "member_change_bps": 300,
        },
        "/api/v1/metrics/daily": {
            "generated_at": generated_at,
            "items": [
                {
                    "metric_observation_key": "enterprise:PAID_GMV_FEN:2026-08-24",
                    "scope_type": "enterprise",
                    "shop_code": None,
                    "indicator_code": "PAID_GMV_FEN",
                    "business_date": "2026-08-24",
                    "value": 120000,
                    "change_bps": 250,
                },
                {
                    "metric_observation_key": "EXT-001:PAID_ORDER_COUNT:2026-08-24",
                    "scope_type": "shop",
                    "shop_code": "EXT-001",
                    "indicator_code": "PAID_ORDER_COUNT",
                    "business_date": "2026-08-24",
                    "value": 18,
                    "change_bps": -100,
                },
            ],
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payloads[request.url.path])

    connector = MockCommerceConnector(
        "http://vendor.test",
        transport=httpx.MockTransport(handler),
    )
    batch = await connector.fetch("normal")

    metrics = {item.key: item for item in batch.metrics}
    assert batch.source_schema_version == "vendor-7"
    assert metrics["gmv_today"].value == 1234.56
    assert metrics["refund_rate"].value == 5.15
    assert metrics["ad_roi"].value == 3.18
    history = [item for item in batch.metrics if item.as_of.date().isoformat() == "2026-08-24"]
    assert {(item.key, item.scope_key) for item in history} == {
        ("gmv_today", "enterprise"),
        ("orders_today", "store-flagship"),
    }
    assert next(item for item in history if item.key == "gmv_today").value == 1200
    assert batch.entities[0].canonical_key == "EXT-001"
    assert batch.entities[0].display_name == "外部旗舰店"
    assert len(batch.scope_mappings) == 1
    assert batch.scope_mappings[0].external_scope_key == "EXT-001"
    assert batch.scope_mappings[0].scope_key == "store-flagship"
    assert batch.scope_mappings[0].label == "外部旗舰店"
    assert batch.mapping_version == "1.2.0"
    assert {item.entity_type for item in batch.entities} == {
        "store",
        "product",
        "sku",
        "warehouse",
        "customer",
        "order",
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    (
        "profile",
        "schema_key",
        "entity_path",
        "entity_item",
        "entity_type",
        "metric_code",
        "metric_key",
    ),
    [
        (
            "erp-oms",
            "erp_oms",
            "/api/v1/shops",
            {
                "shop_code": "TM-001",
                "shop_title": "旗舰店",
                "channel": "tmall",
                "shop_state": "ACTIVE",
                "manager_name": "经理",
            },
            "store",
            "PAID_GMV_FEN",
            "gmv_today",
        ),
        (
            "crm",
            "crm",
            "/api/v1/customers",
            {
                "customer_code": "CUS-0000001",
                "customer_name": "会员 1",
                "member_state": "ACTIVE",
                "member_segment": "高价值",
                "province_name": "浙江",
                "total_order_count": 8,
            },
            "customer",
            "ACTIVE_MEMBER_COUNT",
            "active_members",
        ),
        (
            "advertising",
            "advertising",
            "/api/v1/ads/campaigns",
            {
                "campaign_code": "ADP-000001",
                "campaign_name": "增长计划",
                "campaign_state": "RUNNING",
                "shop_code": "TM-001",
                "channel": "万相台",
                "daily_budget_fen": 100000,
                "owner_team": "投放组",
            },
            "ad_campaign",
            "AD_ROI_X100",
            "ad_roi",
        ),
        (
            "customer-service",
            "customer_service",
            "/api/v1/service/conversations",
            {
                "conversation_code": "CSV-0000001",
                "conversation_state": "OPEN",
                "shop_code": "TM-001",
                "customer_code": "CUS-0000001",
                "order_code": "ORD-000001",
                "channel": "天猫旺旺",
                "risk_level": "normal",
            },
            "service_conversation",
            "SERVICE_CONVERSATION_COUNT",
            "service_conversations",
        ),
    ],
)
async def test_source_profiles_keep_vendor_resources_inside_owned_connector_boundary(
    profile: ConnectorProfile,
    schema_key: str,
    entity_path: str,
    entity_item: dict[str, object],
    entity_type: str,
    metric_code: str,
    metric_key: str,
) -> None:
    generated_at = datetime.now(UTC).isoformat()
    observed_domains: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/profile":
            return httpx.Response(
                200,
                json={
                    "schema_version": "aggregate-v1",
                    "source_schemas": {schema_key: f"{schema_key}-v7"},
                    "generated_at": generated_at,
                },
            )
        if request.url.path == "/api/v1/metrics/daily":
            observed_domains.append(request.url.params["domain"])
            return httpx.Response(
                200,
                json={
                    "generated_at": generated_at,
                    "items": [
                        {
                            "metric_observation_key": f"enterprise:{metric_code}:2026-08-29",
                            "scope_type": "enterprise",
                            "shop_code": None,
                            "indicator_code": metric_code,
                            "business_date": "2026-08-29",
                            "value": 10000,
                            "change_bps": 100,
                        }
                    ],
                },
            )
        if request.url.path == entity_path:
            return httpx.Response(200, json={"generated_at": generated_at, "items": [entity_item]})
        if request.url.path.endswith("/summary"):
            return httpx.Response(503, json={"detail": "summary omitted by contract fixture"})
        return httpx.Response(200, json={"generated_at": generated_at, "items": []})

    connector = MockCommerceConnector(
        "http://vendor.test",
        transport=httpx.MockTransport(handler),
        profile=profile,
    )
    batch = await connector.fetch("normal", "small")

    assert batch.source_schema_version == f"{schema_key}-v7"
    assert {item.entity_type for item in batch.entities} == {entity_type}
    assert {item.key for item in batch.metrics} == {metric_key}
    assert observed_domains == [profile]
    if profile == "crm":
        assert batch.customer_profiles == ()
        assert "customer_profiles" not in batch.authoritative_fact_types
        assert any("incomplete customer profile fields" in item for item in batch.warnings)
