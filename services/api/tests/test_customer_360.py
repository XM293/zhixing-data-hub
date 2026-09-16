from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api import data_center_service
from zhixing_api.config import Settings
from zhixing_api.connectors.contracts import (
    CanonicalCustomerProfile,
    CanonicalCustomerTouchpointFact,
    CanonicalEntity,
    CanonicalOrderFact,
    CanonicalRefundFact,
    CanonicalScopeMapping,
    ConnectorBatch,
    ExternalRecord,
)
from zhixing_api.data_models import (
    AuthorizationDecision,
    CustomerProfile,
    CustomerTouchpointFact,
    ToolDefinition,
    ToolInvocation,
)
from zhixing_api.main import create_app

ADMIN_HEADERS = {"X-Zhixing-Demo-Actor": "admin"}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://test",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'customer_360_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


def _scope_mappings() -> tuple[CanonicalScopeMapping, ...]:
    return (
        CanonicalScopeMapping(
            "store", "store-flagship", "TM-001", "天猫旗舰店", "active", {"channel": "tmall"}
        ),
        CanonicalScopeMapping(
            "store", "store-outlet", "JD-002", "京东自营店", "active", {"channel": "jd"}
        ),
    )


def _crm_batch() -> ConnectorBatch:
    observed_at = datetime(2026, 8, 27, 12, tzinfo=UTC)
    profiles = (
        CanonicalCustomerProfile(
            "CUS-001", "会员 00001", "TM-001", "gold", "mature", "active", "浙江",
            "tmall", observed_at, observed_at, 1200, 3800, 0.22, "护肤", "granted",
            ("高价值", "护肤"),
        ),
        CanonicalCustomerProfile(
            "CUS-002", "会员 00002", "TM-001", "silver", "at_risk", "active", "江苏",
            "tmall", observed_at, observed_at, 260, 900, 0.82, "个护", "granted",
            ("流失预警", "个护"),
        ),
        CanonicalCustomerProfile(
            "CUS-003", "会员 00003", "JD-002", "standard", "new", "active", "广东",
            "jd", observed_at, observed_at, 80, 240, 0.18, "食品", "revoked",
            ("新客", "食品"),
        ),
    )
    touchpoints = (
        CanonicalCustomerTouchpointFact(
            "EVT-001", "CUS-001", "TM-001", "visit", "tmall", observed_at,
            None, 0, {"device_type": "mobile"},
        ),
        CanonicalCustomerTouchpointFact(
            "EVT-002", "CUS-001", "TM-001", "add_to_cart", "tmall", observed_at,
            None, 12_000, {"product_key": "SPU-001"},
        ),
        CanonicalCustomerTouchpointFact(
            "EVT-003", "CUS-002", "TM-001", "campaign_click", "tmall", observed_at,
            "CRM-CAM-001", 0, {"product_key": "SPU-002"},
        ),
        CanonicalCustomerTouchpointFact(
            "EVT-004", "CUS-003", "JD-002", "service", "jd", observed_at,
            None, 0, {"session_key": "SES-001"},
        ),
    )
    return ConnectorBatch(
        source_schema_version="CRM-2026.08",
        mapping_version="1.2.0",
        records=(ExternalRecord("customers", "CUS-001", {"customer": "001"}, observed_at),),
        entities=tuple(
            CanonicalEntity(
                "customer", item.customer_key, item.display_name, item.status,
                {"lifecycle_stage": item.lifecycle_stage},
            )
            for item in profiles
        ),
        metrics=(),
        warnings=(),
        scope_mappings=_scope_mappings(),
        customer_profiles=profiles,
        customer_touchpoints=touchpoints,
        authoritative_fact_types=("customer_profiles", "customer_touchpoints"),
    )


def _erp_batch() -> ConnectorBatch:
    paid_at = datetime(2026, 8, 25, 10, tzinfo=UTC)
    order_inputs = (
        ("ORD-001", "TM-001", "CUS-001", 10_000),
        ("ORD-002", "TM-001", "CUS-001", 15_000),
        ("ORD-003", "TM-001", "CUS-002", 20_000),
        ("ORD-004", "JD-002", "CUS-003", 30_000),
    )
    orders = tuple(
        CanonicalOrderFact(
            order_key,
            store_key,
            customer_key,
            "tmall" if store_key == "TM-001" else "jd",
            "completed",
            date(2026, 8, 25),
            paid_at,
            paid_at,
            paid_amount,
            paid_amount,
            0,
            0,
            round(paid_amount * 0.6),
            1,
            "浙江",
        )
        for order_key, store_key, customer_key, paid_amount in order_inputs
    )
    refunds = (
        CanonicalRefundFact(
            "REF-001", "ORD-002", "LINE-002", "TM-001", "CUS-001", "SKU-001",
            "quality", "completed", paid_at, paid_at, 5_000, 1,
        ),
    )
    return ConnectorBatch(
        source_schema_version="JKY-ERP-2026.08",
        mapping_version="1.4.0",
        records=(ExternalRecord("orders/recent", "ORD-001", {"order": "001"}, paid_at),),
        entities=(
            CanonicalEntity("store", "TM-001", "天猫旗舰店", "active", {"channel": "tmall"}),
            CanonicalEntity("store", "JD-002", "京东自营店", "active", {"channel": "jd"}),
        ),
        metrics=(),
        warnings=(),
        scope_mappings=_scope_mappings(),
        orders=orders,
        refunds=refunds,
        authoritative_fact_types=("orders", "refunds"),
    )


@pytest.mark.anyio
async def test_customer_360_is_traceable_scoped_and_available_through_mcp_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batches = {"test-crm": _crm_batch(), "test-erp-oms": _erp_batch()}

    class StubConnector:
        def __init__(self, batch: ConnectorBatch) -> None:
            self.batch = batch

        async def fetch(self, _scenario: str, _volume_profile: str = "standard") -> ConnectorBatch:
            return self.batch

    monkeypatch.setattr(
        data_center_service,
        "create_connector",
        lambda system_type, _base_url: StubConnector(batches[system_type]),
    )
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        for _ in range(2):
            assert (await client.post(
                "/api/v1/data-center/sources/crm-members/sync",
                json={"scenario": "normal", "volume_profile": "small"},
            )).status_code == 200
            await data_center_service.synchronize(
                app.state.database, app.state.settings, "normal", "small",
                source_key="crm-members", enterprise_id="ent_zhixing_demo", execute=True,
            )
        assert (await client.post(
            "/api/v1/data-center/sources/jky-erp-oms/sync",
            json={"scenario": "normal", "volume_profile": "small"},
        )).status_code == 200
        await data_center_service.synchronize(
            app.state.database, app.state.settings, "normal", "small",
            source_key="jky-erp-oms", enterprise_id="ent_zhixing_demo", execute=True,
        )
        ceo = await client.get(
            "/api/v1/data-center/customer-360",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )
        employee_store = await client.get(
            "/api/v1/data-center/customer-360",
            params={"scope_key": "store-flagship"},
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        employee_enterprise = await client.get(
            "/api/v1/data-center/customer-360",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        detail = await client.get(
            "/api/v1/data-center/customer-360/CUS-001",
            params={"scope_key": "enterprise"},
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )
        employee_detail = await client.get(
            "/api/v1/data-center/customer-360/CUS-001",
            params={"scope_key": "store-flagship"},
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        employee_other_store = await client.get(
            "/api/v1/data-center/customer-360/CUS-003",
            params={"scope_key": "store-flagship"},
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        tool = await client.post(
            "/api/v1/tools/query_customer_360/invoke",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"parameters": {"scope_key": "enterprise", "limit": 2}},
        )
        detail_tool = await client.post(
            "/api/v1/tools/query_customer_360/invoke",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={
                "parameters": {
                    "scope_key": "enterprise",
                    "customer_key": "CUS-001",
                    "limit": 20,
                }
            },
        )

    assert ceo.status_code == 200
    summary = ceo.json()["summary"]
    assert summary == {
        "profile_count": 3,
        "active_customer_count": 3,
        "consented_customer_count": 2,
        "at_risk_customer_count": 1,
        "purchasing_customer_count": 3,
        "repeat_customer_count": 1,
        "repeat_purchase_rate": pytest.approx(0.3333),
        "paid_gmv_yuan": 750.0,
        "average_customer_value_yuan": 250.0,
        "touchpoint_count": 4,
    }
    assert {item["key"] for item in ceo.json()["lineage"]} == {
        "profiles", "touchpoints", "orders"
    }
    assert employee_store.status_code == 200
    assert employee_store.json()["summary"]["profile_count"] == 2
    assert employee_store.json()["summary"]["paid_gmv_yuan"] == 450.0
    assert employee_enterprise.status_code == 403
    assert employee_enterprise.json()["error"]["code"] == "authorization.scope_denied"
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["profile"]["member_points"] == 1200
    assert detail_payload["summary"]["lifetime_order_count"] == 2
    assert detail_payload["summary"]["paid_gmv_yuan"] == 250.0
    assert detail_payload["summary"]["refund_amount_yuan"] == 50.0
    assert detail_payload["summary"]["refund_rate"] == pytest.approx(0.2)
    assert {item["event_type"] for item in detail_payload["timeline"]} == {
        "profile", "order", "refund", "touchpoint"
    }
    assert detail_payload["recommendation_mode"] == "deterministic_playbook"
    assert all(item["evidence_keys"] for item in detail_payload["recommendations"])
    assert employee_detail.status_code == 200
    assert employee_other_store.status_code == 404
    assert employee_other_store.json()["error"]["code"] == "customer.profile_not_found"
    assert tool.status_code == 200
    assert len(tool.json()["output"]["customers"]) == 2
    assert detail_tool.status_code == 200
    assert detail_tool.json()["output"]["customer_key"] == "CUS-001"
    assert len(detail_tool.json()["output"]["orders"]) == 2
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(CustomerProfile.id))) == 3
        assert session.scalar(select(func.count(CustomerTouchpointFact.id))) == 4
        assert session.scalar(select(func.count(ToolInvocation.id))) == 2
        assert session.scalar(select(func.count(ToolDefinition.id))) == 5
        decisions = list(
            session.scalars(
                select(AuthorizationDecision).where(
                    AuthorizationDecision.permission_key == "customer.profile.read"
                )
            )
        )
    assert {item.decision for item in decisions} == {"allow", "deny"}


@pytest.mark.anyio
async def test_partial_crm_batch_preserves_touchpoints_until_authoritative_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = {"batch": _crm_batch()}

    class StubConnector:
        async def fetch(self, _scenario: str, _volume_profile: str = "standard") -> ConnectorBatch:
            return current["batch"]

    monkeypatch.setattr(
        data_center_service,
        "create_connector",
        lambda _system_type, _base_url: StubConnector(),
    )
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        await client.post(
            "/api/v1/data-center/sources/crm-members/sync",
            json={"scenario": "normal", "volume_profile": "small"},
        )
        await data_center_service.synchronize(
            app.state.database, app.state.settings, "normal", "small",
            source_key="crm-members", enterprise_id="ent_zhixing_demo", execute=True,
        )
        current["batch"] = replace(
            current["batch"],
            customer_profiles=current["batch"].customer_profiles[:2],
            customer_touchpoints=(),
            authoritative_fact_types=("customer_profiles",),
        )
        await client.post(
            "/api/v1/data-center/sources/crm-members/sync",
            json={"scenario": "partial", "volume_profile": "small"},
        )
        await data_center_service.synchronize(
            app.state.database, app.state.settings, "partial", "small",
            source_key="crm-members", enterprise_id="ent_zhixing_demo", execute=True,
        )
        with app.state.database.session() as session:
            assert session.scalar(select(func.count(CustomerProfile.id))) == 2
            assert session.scalar(select(func.count(CustomerTouchpointFact.id))) == 4
        current["batch"] = replace(
            current["batch"],
            customer_touchpoints=_crm_batch().customer_touchpoints[:1],
            authoritative_fact_types=("customer_profiles", "customer_touchpoints"),
        )
        await client.post(
            "/api/v1/data-center/sources/crm-members/sync",
            json={"scenario": "normal", "volume_profile": "small"},
        )
        await data_center_service.synchronize(
            app.state.database, app.state.settings, "normal", "small",
            source_key="crm-members", enterprise_id="ent_zhixing_demo", execute=True,
        )

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(CustomerProfile.id))) == 2
        assert session.scalar(select(func.count(CustomerTouchpointFact.id))) == 1
