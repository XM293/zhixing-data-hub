from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api import data_center_service
from zhixing_api.config import Settings
from zhixing_api.connectors.contracts import (
    CanonicalAdPerformanceFact,
    CanonicalEntity,
    CanonicalInventorySnapshotFact,
    CanonicalOrderFact,
    CanonicalOrderLineFact,
    CanonicalRefundFact,
    CanonicalScopeMapping,
    ConnectorBatch,
    ExternalRecord,
)
from zhixing_api.data_models import (
    CommerceAdPerformanceFact,
    CommerceInventorySnapshotFact,
    CommerceOrderFact,
    CommerceOrderLineFact,
    CommerceRefundFact,
    DataScopeMapping,
)
from zhixing_api.main import create_app

ADMIN_HEADERS = {"X-Zhixing-Demo-Actor": "admin"}


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'commerce.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


def _erp_batch() -> ConnectorBatch:
    paid_at = datetime(2026, 8, 25, 10, tzinfo=UTC)
    orders = (
        CanonicalOrderFact(
            order_key="ORD-001",
            store_key="TM-001",
            customer_key="CUS-001",
            channel="tmall",
            status="completed",
            business_date=date(2026, 8, 25),
            paid_at=paid_at,
            shipped_at=paid_at,
            paid_amount_fen=20_000,
            item_amount_fen=22_000,
            discount_amount_fen=2_000,
            freight_amount_fen=0,
            cost_amount_fen=12_000,
            item_count=1,
            province="浙江",
        ),
        CanonicalOrderFact(
            order_key="ORD-002",
            store_key="JD-002",
            customer_key="CUS-002",
            channel="jd",
            status="shipped",
            business_date=date(2026, 8, 25),
            paid_at=paid_at,
            shipped_at=paid_at,
            paid_amount_fen=30_000,
            item_amount_fen=31_000,
            discount_amount_fen=1_000,
            freight_amount_fen=0,
            cost_amount_fen=18_000,
            item_count=2,
            province="江苏",
        ),
    )
    return ConnectorBatch(
        source_schema_version="JKY-ERP-2026.08",
        mapping_version="1.4.0",
        records=(
            ExternalRecord("orders/recent", "ORD-001", {"order": "001"}, paid_at),
        ),
        entities=(
            CanonicalEntity(
                "store",
                "TM-001",
                "天猫旗舰店",
                "active",
                {"channel": "tmall"},
            ),
            CanonicalEntity(
                "store",
                "JD-002",
                "京东自营店",
                "active",
                {"channel": "jd"},
            ),
        ),
        metrics=(),
        warnings=(),
        scope_mappings=(
            CanonicalScopeMapping(
                "store",
                "store-flagship",
                "TM-001",
                "天猫旗舰店",
                "active",
                {"channel": "tmall"},
            ),
            CanonicalScopeMapping(
                "store",
                "store-outlet",
                "JD-002",
                "京东自营店",
                "active",
                {"channel": "jd"},
            ),
        ),
        orders=orders,
        order_lines=(
            CanonicalOrderLineFact(
                "ORD-001-L01", "ORD-001", "SPU-001", "SKU-001", 1,
                20_000, 20_000, 12_000, 1, 5_000,
            ),
            CanonicalOrderLineFact(
                "ORD-002-L01", "ORD-002", "SPU-001", "SKU-001", 1,
                15_000, 15_000, 9_000, 1, 4_000,
            ),
            CanonicalOrderLineFact(
                "ORD-002-L02", "ORD-002", "SPU-002", "SKU-002", 1,
                15_000, 15_000, 9_000, 0, 0,
            ),
        ),
        refunds=(
            CanonicalRefundFact(
                "RFD-001", "ORD-001", "ORD-001-L01", "TM-001", "CUS-001",
                "SKU-001", "商品质量", "completed", paid_at, paid_at, 5_000, 1,
            ),
            CanonicalRefundFact(
                "RFD-002", "ORD-002", "ORD-002-L01", "JD-002", "CUS-002",
                "SKU-001", "描述不符", "approved", paid_at, None, 4_000, 1,
            ),
        ),
        inventory=(
            CanonicalInventorySnapshotFact(
                "WH-001:SKU-001:2026-08-25", "WH-001", "SPU-001", "SKU-001",
                paid_at, 10, 4, 20, 30, 50_000, 1.5, "low",
            ),
            CanonicalInventorySnapshotFact(
                "WH-001:SKU-002:2026-08-25", "WH-001", "SPU-002", "SKU-002",
                paid_at, 80, 5, 10, 30, 180_000, 18.0, "healthy",
            ),
        ),
        authoritative_fact_types=("orders", "order_lines", "refunds", "inventory"),
    )


def _advertising_batch() -> ConnectorBatch:
    observed_at = datetime(2026, 8, 25, 12, tzinfo=UTC)
    return ConnectorBatch(
        source_schema_version="ADS-2026.07",
        mapping_version="1.2.0",
        records=(ExternalRecord("ads/performance", "AD-001", {"ad": "001"}, observed_at),),
        entities=(),
        metrics=(),
        warnings=(),
        advertising=(
            CanonicalAdPerformanceFact(
                "AD-001:2026-08-24", "AD-001", "TM-001", "SPU-001", "万相台",
                date(2026, 8, 24), 10_000, 200, 10_000, 3, 18_000,
            ),
            CanonicalAdPerformanceFact(
                "AD-002:2026-08-25", "AD-002", "JD-002", "SPU-002", "京准通",
                date(2026, 8, 25), 12_000, 300, 8_000, 5, 30_000,
            ),
        ),
        authoritative_fact_types=("advertising",),
    )


@pytest.mark.anyio
async def test_authoritative_fact_batch_prunes_stale_source_refunds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_batch = {"value": _erp_batch()}

    class StubConnector:
        async def fetch(
            self, _scenario: str, _volume_profile: str = "standard"
        ) -> ConnectorBatch:
            return current_batch["value"]

    monkeypatch.setattr(
        data_center_service,
        "create_connector",
        lambda _system_type, _base_url: StubConnector(),
    )
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=ADMIN_HEADERS
    ) as client:
        first = await client.post(
            "/api/v1/data-center/sources/jky-erp-oms/sync",
            json={"scenario": "normal", "volume_profile": "small"},
        )
        await data_center_service.synchronize(
            app.state.database, app.state.settings, "normal", "small",
            source_key="jky-erp-oms", enterprise_id="ent_zhixing_demo", execute=True,
        )
        current_batch["value"] = replace(
            current_batch["value"],
            refunds=current_batch["value"].refunds[:1],
        )
        second = await client.post(
            "/api/v1/data-center/sources/jky-erp-oms/sync",
            json={"scenario": "normal", "volume_profile": "small"},
        )
        await data_center_service.synchronize(
            app.state.database, app.state.settings, "normal", "small",
            source_key="jky-erp-oms", enterprise_id="ent_zhixing_demo", execute=True,
        )

    assert first.status_code == second.status_code == 200
    with app.state.database.session() as session:
        refunds = list(session.scalars(select(CommerceRefundFact)))
    assert [item.refund_key for item in refunds] == ["RFD-001"]


@pytest.mark.anyio
async def test_commerce_facts_are_idempotent_traceable_and_queryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batches = {"test-erp-oms": _erp_batch(), "test-advertising": _advertising_batch()}

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
            erp = await client.post(
                "/api/v1/data-center/sources/jky-erp-oms/sync",
                json={"scenario": "normal", "volume_profile": "small"},
            )
            ads = await client.post(
                "/api/v1/data-center/sources/advertising-platforms/sync",
                json={"scenario": "normal", "volume_profile": "small"},
            )
            assert erp.status_code == ads.status_code == 200
            await data_center_service.synchronize(
                app.state.database, app.state.settings, "normal", "small",
                source_key="jky-erp-oms", enterprise_id="ent_zhixing_demo", execute=True,
            )
            await data_center_service.synchronize(
                app.state.database, app.state.settings, "normal", "small",
                source_key="advertising-platforms", enterprise_id="ent_zhixing_demo", execute=True,
            )
        response = await client.get("/api/v1/data-center/commerce-operations")
        flagship = await client.get(
            "/api/v1/data-center/commerce-operations",
            params={"scope_key": "store-flagship"},
        )
        employee_store = await client.post(
            "/api/v1/tools/query_commerce_facts/invoke",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={"parameters": {"scope_key": "store-flagship", "limit": 10}},
        )
        employee_enterprise = await client.post(
            "/api/v1/tools/query_commerce_facts/invoke",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={"parameters": {"scope_key": "enterprise", "limit": 10}},
        )
        ceo_enterprise = await client.post(
            "/api/v1/tools/query_commerce_facts/invoke",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"parameters": {"scope_key": "enterprise", "limit": 10}},
        )
        overview = await client.get("/api/v1/data-center/overview")
        reconciliation_quality = await client.get(
            "/api/v1/data-center/quality", params={"query": "客服订单"}
        )

    assert response.status_code == 200
    assert flagship.status_code == 200
    assert flagship.json()["summary"]["order_count"] == 1
    assert flagship.json()["summary"]["inventory_sku_count"] == 0
    assert {item["store_key"] for item in flagship.json()["stores"]} == {"TM-001"}
    assert employee_store.status_code == 200
    assert employee_store.json()["output"]["summary"]["order_count"] == 1
    assert employee_enterprise.status_code == 403
    assert employee_enterprise.json()["error"]["code"] == "authorization.scope_denied"
    assert ceo_enterprise.status_code == 200
    assert ceo_enterprise.json()["output"]["summary"]["order_count"] == 2
    assert overview.status_code == 200
    assert overview.json()["schema_version"] == 9
    assert overview.json()["commerce_fact_count"] == 11
    assert reconciliation_quality.status_code == 200
    quality_item = reconciliation_quality.json()["items"][0]
    assert quality_item["result_status"] == "warning"
    assert quality_item["affected_records"] == 10
    assert quality_item["details"]["missing_count"] == 10
    assert len(quality_item["details"]["issues"]) == 10
    payload = response.json()
    assert payload["summary"]["order_count"] == 2
    assert payload["summary"]["order_line_count"] == 3
    assert payload["summary"]["paid_gmv_yuan"] == 500
    assert payload["summary"]["gross_margin_rate"] == pytest.approx(0.4)
    assert payload["summary"]["refund_amount_yuan"] == 90
    assert payload["summary"]["inventory_sku_count"] == 2
    assert payload["summary"]["low_stock_sku_count"] == 1
    assert payload["summary"]["advertising_roi"] == pytest.approx(2.6667)
    assert {item["store_key"] for item in payload["stores"]} == {"TM-001", "JD-002"}
    assert {item["exception_type"] for item in payload["exceptions"]} >= {
        "inventory",
        "refund",
        "advertising",
    }
    assert payload["recent_orders"][0]["sync_run_id"].startswith("sync_")
    assert {item["key"] for item in payload["lineage"]} == {
        "orders",
        "order-lines",
        "refunds",
        "inventory",
        "advertising",
    }
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(CommerceOrderFact.id))) == 2
        assert session.scalar(select(func.count(CommerceOrderLineFact.id))) == 3
        assert session.scalar(select(func.count(CommerceRefundFact.id))) == 2
        assert session.scalar(select(func.count(CommerceInventorySnapshotFact.id))) == 2
        assert session.scalar(select(func.count(CommerceAdPerformanceFact.id))) == 2
        assert session.scalar(select(func.count(DataScopeMapping.id))) == 2
