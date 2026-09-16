import pytest
from httpx import ASGITransport, AsyncClient

from mock_commerce.main import create_app


@pytest.mark.anyio
async def test_normal_scenario_exposes_provider_shaped_data() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        profile = await client.get("/api/v1/profile")
        orders = await client.get("/api/v1/orders/summary")
        products = await client.get("/api/v1/products")
        skus = await client.get("/api/v1/skus")

    assert profile.status_code == 200
    assert profile.json()["schema_version"] == "2026.08"
    assert orders.json()["paid_gmv_fen"] == 238648900
    assert "gmv_today" not in orders.json()
    assert len(products.json()["items"]) == 36
    assert len(skus.json()["items"]) == 144


@pytest.mark.anyio
async def test_volume_profiles_are_deterministic_and_change_scale() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        small = await client.get("/api/v1/orders/recent", params={"volume": "small"})
        large = await client.get("/api/v1/orders/recent", params={"volume": "large"})
        repeated = await client.get("/api/v1/orders/recent", params={"volume": "small"})

    assert len(small.json()["items"]) == 24
    assert len(large.json()["items"]) == 1200
    assert small.json()["items"] == repeated.json()["items"]


@pytest.mark.anyio
async def test_large_profile_contains_customer_service_reconciliation_records() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        orders = await client.get("/api/v1/orders/recent", params={"volume": "large"})
        refunds = await client.get("/api/v1/refunds", params={"volume": "large"})

    by_key = {item["order_code"]: item for item in orders.json()["items"]}
    assert by_key["ORD-20260825-000422"]["paid_amount_fen"] == 39_900
    assert by_key["ORD-20260825-000422"]["item_count"] == 1
    assert by_key["ORD-20260825-000422"]["order_state"] == "SHIPPED"
    assert by_key["ORD-20260825-000214"]["order_state"] == "REFUNDED"
    assert by_key["ORD-20260825-000529"]["paid_amount_fen"] == 56_051

    refund_order_keys = {item["order_code"] for item in refunds.json()["items"]}
    assert "ORD-20260825-000214" in refund_order_keys
    assert "ORD-20260825-000406" not in refund_order_keys
    assert "ORD-20260825-000476" not in refund_order_keys


@pytest.mark.anyio
async def test_daily_metrics_expose_90_days_for_enterprise_and_store_scopes() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        first = await client.get("/api/v1/metrics/daily", params={"volume": "standard"})
        repeated = await client.get("/api/v1/metrics/daily", params={"volume": "standard"})

    assert first.status_code == 200
    payload = first.json()
    assert payload["history_days"] == 90
    assert payload["business_date_from"] == "2026-05-30"
    assert payload["business_date_to"] == "2026-08-27"
    assert payload["items"] == repeated.json()["items"]
    assert {item["scope_type"] for item in payload["items"]} == {"enterprise", "shop"}
    enterprise_indicators = {
        item["indicator_code"] for item in payload["items"] if item["scope_type"] == "enterprise"
    }
    assert len(enterprise_indicators) == 21
    assert enterprise_indicators.issuperset(
        {
            "ACTIVE_MEMBER_COUNT",
            "AD_ROI_X100",
            "LOW_STOCK_SKU_COUNT",
            "PAID_GMV_FEN",
            "PAID_ORDER_COUNT",
            "REFUND_RATE_BPS",
            "SERVICE_CONVERSATION_COUNT",
        }
    )
    assert len({item["business_date"] for item in payload["items"]}) == 90
    assert all(item["metric_observation_key"] for item in payload["items"])


@pytest.mark.anyio
async def test_source_domains_expose_independent_deterministic_payloads() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        campaigns = await client.get("/api/v1/ads/campaigns", params={"volume": "large"})
        conversations = await client.get(
            "/api/v1/service/conversations", params={"volume": "large"}
        )
        crm_metrics = await client.get(
            "/api/v1/metrics/daily",
            params={"volume": "small", "domain": "crm"},
        )
        advertising_metrics = await client.get(
            "/api/v1/metrics/daily",
            params={"volume": "small", "domain": "advertising"},
        )
        customer_profiles = await client.get(
            "/api/v1/customers", params={"volume": "large"}
        )
        touchpoints = await client.get(
            "/api/v1/crm/touchpoints", params={"volume": "large"}
        )
        repeated_touchpoints = await client.get(
            "/api/v1/crm/touchpoints", params={"volume": "large"}
        )

    assert len(campaigns.json()["items"]) == 480
    assert len(conversations.json()["items"]) == 2400
    assert {item["indicator_code"] for item in crm_metrics.json()["items"]} == {
        "ACTIVE_MEMBER_COUNT",
        "NEW_MEMBER_COUNT",
        "REPEAT_PURCHASE_RATE_BPS",
        "CHURN_RISK_MEMBER_COUNT",
    }
    assert {item["indicator_code"] for item in advertising_metrics.json()["items"]} == {
        "AD_ROI_X100",
        "AD_SPEND_FEN",
        "ATTRIBUTED_REVENUE_FEN",
        "AD_CTR_BPS",
        "AD_CONVERSION_RATE_BPS",
    }
    assert len(customer_profiles.json()["items"]) == 600
    assert len(touchpoints.json()["items"]) == 3600
    assert touchpoints.json()["items"] == repeated_touchpoints.json()["items"]
    first_customer = customer_profiles.json()["items"][0]
    assert first_customer["home_shop_code"]
    assert 0 <= first_customer["churn_risk_score_x10000"] <= 10_000
    assert set(touchpoints.json()["items"][0]) >= {
        "touchpoint_code",
        "customer_code",
        "shop_code",
        "event_type",
        "occurred_at",
    }


@pytest.mark.anyio
async def test_partial_scenario_only_fails_ads_resource() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        ads = await client.get("/api/v1/ads/summary", params={"scenario": "partial"})
        orders = await client.get("/api/v1/orders/summary", params={"scenario": "partial"})
        crm_profiles = await client.get("/api/v1/customers", params={"scenario": "partial"})
        crm_touchpoints = await client.get(
            "/api/v1/crm/touchpoints", params={"scenario": "partial"}
        )

    assert ads.status_code == 503
    assert orders.status_code == 200
    assert crm_profiles.status_code == 200
    assert crm_touchpoints.status_code == 503
