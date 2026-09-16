from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.ai_provider import AICompletion
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    BusinessAnalysisRun,
    BusinessBrief,
    CommerceAdPerformanceFact,
    CommerceInventorySnapshotFact,
    CommerceOrderFact,
    CommerceRefundFact,
    EvidenceSnapshot,
    EvidenceSnapshotItem,
    MetricSnapshot,
    SyncRun,
)
from zhixing_api.main import create_app


def make_settings(tmp_path: Path, *, ai_enabled: bool = False) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'analysis_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
        ai_enabled=ai_enabled,
        ai_api_key="test-key" if ai_enabled else "",
        ai_model="analysis-test-model",
    )


def seed_metric_series(app: object) -> None:
    database = app.state.database  # type: ignore[attr-defined]
    start = datetime(2026, 7, 29, tzinfo=UTC)
    values = {
        "gmv_today": (1_200_000.0, 18_000.0, "元"),
        "orders_today": (6_200.0, 80.0, "单"),
        "refund_rate": (5.1, 0.025, "%"),
        "ad_roi": (3.15, 0.01, "x"),
    }
    labels = {
        "gmv_today": "今日成交",
        "orders_today": "支付订单",
        "refund_rate": "退款率",
        "ad_roi": "广告 ROI",
    }
    with database.session() as session:
        for scope_key in ("enterprise", "store-flagship", "store-outlet"):
            for day in range(30):
                as_of = start + timedelta(days=day)
                for metric_key, (base, step, unit) in values.items():
                    value = base + step * day
                    if metric_key == "refund_rate" and day == 12:
                        value = 5.72
                    if metric_key == "ad_roi" and day == 18:
                        value = 2.42
                    session.add(
                        MetricSnapshot(
                            id=f"metric_{scope_key}_{metric_key}_{day:02d}",
                            enterprise_id="ent_zhixing_demo",
                            source_system_id=None,
                            sync_run_id=None,
                            metric_key=metric_key,
                            label=labels[metric_key],
                            scope_key=scope_key,
                            value=value,
                            unit=unit,
                            change_rate=None,
                            as_of=as_of,
                        )
                    )
        session.commit()


def seed_commerce_facts(app: object) -> None:
    database = app.state.database  # type: ignore[attr-defined]
    now = datetime(2026, 8, 27, 12, tzinfo=UTC)
    common = {
        "enterprise_id": "ent_zhixing_demo",
        "external_system_id": "source_mock_commerce",
        "sync_run_id": "sync_analysis_commerce",
        "created_at": now,
        "updated_at": now,
    }
    with database.session() as session:
        session.add(
            SyncRun(
                id="sync_analysis_commerce",
                enterprise_id="ent_zhixing_demo",
                external_system_id="source_mock_commerce",
                status="succeeded",
                scenario="normal",
                volume_profile="small",
                records_read=5,
                records_written=5,
                warning=None,
                error=None,
                started_at=now,
                finished_at=now,
            )
        )
        session.add(
            CommerceOrderFact(
                id="order_fact_analysis_001",
                order_key="ORD-ANALYSIS-001",
                store_key="TM-001",
                customer_key="CUS-ANALYSIS-001",
                channel="tmall",
                status="completed",
                business_date=now.date(),
                paid_at=now,
                shipped_at=now,
                paid_amount_fen=100_000,
                item_amount_fen=110_000,
                discount_amount_fen=10_000,
                freight_amount_fen=0,
                cost_amount_fen=60_000,
                item_count=2,
                province="浙江",
                **common,
            )
        )
        for index, amount in enumerate((10_000, 7_000), start=1):
            session.add(
                CommerceRefundFact(
                    id=f"refund_fact_analysis_{index}",
                    refund_key=f"RFD-ANALYSIS-{index:03d}",
                    order_key="ORD-ANALYSIS-001",
                    line_key=f"ORD-ANALYSIS-001-L{index:02d}",
                    store_key="TM-001",
                    customer_key="CUS-ANALYSIS-001",
                    sku_key="SKU-RISK-001",
                    reason_category="商品质量",
                    status="completed",
                    requested_at=now,
                    completed_at=now,
                    refund_amount_fen=amount,
                    quantity=1,
                    **common,
                )
            )
        session.add(
            CommerceInventorySnapshotFact(
                id="inventory_fact_analysis_001",
                snapshot_key="WH-001:SKU-RISK-001:2026-08-27",
                warehouse_key="WH-001",
                product_key="SPU-RISK-001",
                sku_key="SKU-RISK-001",
                as_of=now,
                available_quantity=5,
                reserved_quantity=2,
                in_transit_quantity=3,
                safety_quantity=20,
                inventory_cost_fen=50_000,
                days_cover=1.5,
                status="low",
                **common,
            )
        )
        session.add(
            CommerceAdPerformanceFact(
                id="ad_fact_analysis_001",
                performance_key="AD-RISK-001:2026-08-27",
                campaign_key="AD-RISK-001",
                store_key="TM-001",
                product_key="SPU-RISK-001",
                channel="万相台",
                business_date=now.date(),
                impressions=10_000,
                clicks=300,
                spend_fen=10_000,
                attributed_order_count=2,
                attributed_revenue_fen=18_000,
                **common,
            )
        )
        session.commit()


@pytest.mark.anyio
async def test_analysis_fallback_freezes_evidence_generates_brief_and_is_idempotent(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    seed_metric_series(app)
    ceo = {"X-Zhixing-Demo-Actor": "ceo"}
    request_payload = {
        "scope_key": "enterprise",
        "window_days": 30,
        "client_request_key": "analysis-enterprise-fallback-001",
        "workspace_key": "executive",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        empty_studio = await client.get(
            "/api/v1/analysis/studio?scope_key=enterprise", headers=ceo
        )
        created = await client.post(
            "/api/v1/analysis/store-reviews", headers=ceo, json=request_payload
        )
        repeated = await client.post(
            "/api/v1/analysis/store-reviews", headers=ceo, json=request_payload
        )

    assert empty_studio.status_code == 200
    assert empty_studio.json()["stats"]["analysis_run_count"] == 0
    assert created.status_code == 200
    payload = created.json()
    assert payload["idempotent"] is False
    assert payload["run"]["execution_mode"] == "evidence-fallback"
    assert payload["run"]["workspace_key"] == "executive"
    assert payload["run"]["risk_level"] == "high"
    assert len(payload["run"]["result"]["metric_snapshot"]) == 4
    assert payload["run"]["evidence_snapshot"]["item_count"] == 4
    assert payload["brief"]["source_analysis_run_id"] == payload["run"]["id"]
    assert len(payload["brief"]["content"]["sections"]) == 4
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["run"]["id"] == payload["run"]["id"]

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(BusinessAnalysisRun.id))) == 1
        assert session.scalar(select(func.count(BusinessBrief.id))) == 1
        assert session.scalar(select(func.count(EvidenceSnapshot.id))) == 1
        assert session.scalar(select(func.count(EvidenceSnapshotItem.id))) == 4


@pytest.mark.anyio
async def test_analysis_uses_structured_model_and_enforces_role_scope(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path, ai_enabled=True))
    seed_metric_series(app)

    class StubProvider:
        async def generate(self, *_args: object, **_kwargs: object) -> AICompletion:
            return AICompletion(
                payload={
                    "headline": "旗舰店增长恢复，但退款率与投放波动仍需复核",
                    "summary": "成交和订单保持增长，不能仅凭同步上升认定投放增量有效。",
                    "findings": [
                        {
                            "kind": "risk",
                            "severity": "high",
                            "text": "观察窗口内退款率和广告 ROI 均触发过经营阈值。",
                            "evidence_refs": ["E3", "E4"],
                        }
                    ],
                    "recommendations": [
                        {
                            "title": "拆分异常日期",
                            "action": "按渠道、SKU 和广告计划核对异常日期，不直接修改外部账户。",
                            "owner_role": "运营经理",
                            "priority": "high",
                            "evidence_refs": ["E3", "E4"],
                            "success_metric": "退款率回落且广告 ROI 恢复",
                            "stop_condition": "广告 ROI 再次低于现行停止线",
                        }
                    ],
                    "unknowns": ["尚缺广告计划与 SKU 级归因明细。"],
                    "confidence": "medium",
                },
                input_tokens=420,
                output_tokens=180,
            )

    app.state.ai_provider = StubProvider()
    manager = {"X-Zhixing-Demo-Actor": "manager"}
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    admin = {"X-Zhixing-Demo-Actor": "admin"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        manager_enterprise = await client.get(
            "/api/v1/analysis/studio?scope_key=enterprise", headers=manager
        )
        created = await client.post(
            "/api/v1/analysis/store-reviews",
            headers=manager,
            json={
                "scope_key": "store-flagship",
                "window_days": 30,
                "client_request_key": "analysis-store-model-001",
            },
        )
        default_studio = await client.get("/api/v1/analysis/studio", headers=manager)
        employee_read = await client.get(
            "/api/v1/analysis/studio?scope_key=store-flagship", headers=employee
        )
        employee_run = await client.post(
            "/api/v1/analysis/store-reviews",
            headers=employee,
            json={
                "scope_key": "store-flagship",
                "window_days": 30,
                "client_request_key": "analysis-employee-denied-001",
            },
        )
        admin_read = await client.get(
            "/api/v1/analysis/studio?scope_key=enterprise", headers=admin
        )
        admin_run = await client.post(
            "/api/v1/analysis/store-reviews",
            headers=admin,
            json={
                "scope_key": "enterprise",
                "window_days": 30,
                "client_request_key": "analysis-admin-denied-001",
            },
        )

    assert manager_enterprise.status_code == 403
    assert created.status_code == 200
    created_payload = created.json()
    assert created_payload["run"]["execution_mode"] == "model"
    assert created_payload["run"]["provider"] == "openai-compatible-responses"
    assert created_payload["run"]["result"]["headline"].startswith("旗舰店增长恢复")
    assert created_payload["run"]["result"]["findings"][-1]["evidence_refs"] == ["E3", "E4"]
    assert default_studio.status_code == 200
    assert default_studio.json()["selected_scope"]["key"] == "store-flagship"
    assert employee_read.status_code == 200
    assert employee_read.json()["can_run"] is False
    assert employee_run.status_code == 403
    assert employee_run.json()["error"]["code"] == "authorization.permission_denied"
    assert admin_read.status_code == 200
    assert admin_read.json()["can_run"] is False
    assert admin_run.status_code == 403


@pytest.mark.anyio
async def test_analysis_freezes_canonical_commerce_facts_with_lineage(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    seed_metric_series(app)
    seed_commerce_facts(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/analysis/store-reviews",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={
                "scope_key": "enterprise",
                "window_days": 30,
                "client_request_key": "analysis-enterprise-commerce-001",
            },
        )

    assert created.status_code == 200
    run = created.json()["run"]
    facts = run["result"]["commerce_fact_snapshot"]
    assert run["risk_level"] == "critical"
    assert {item["domain"] for item in facts} >= {
        "orders",
        "refunds",
        "inventory",
        "advertising",
        "exception",
    }
    assert all(item["source_keys"] == ["jky-erp-oms"] for item in facts)
    assert all(item["sync_run_ids"] == ["sync_analysis_commerce"] for item in facts)
    assert run["evidence_snapshot"]["item_count"] == 4 + len(facts)
    assert all(item["evidence_ref"].startswith("E") for item in facts)
    with app.state.database.session() as session:
        item_types = set(session.scalars(select(EvidenceSnapshotItem.item_type)))
    assert item_types == {
        "metric-series",
        "commerce-fact-summary",
        "commerce-exception",
    }
