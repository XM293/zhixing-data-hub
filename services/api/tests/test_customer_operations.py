from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.ai_provider import AICompletion
from zhixing_api.config import Settings
from zhixing_api.data_models import (
    ActionApprovalEvent,
    ActionExecution,
    ActionProposal,
    CommerceOrderFact,
    CommerceRefundFact,
    CustomerOperationRun,
    CustomerProfile,
    CustomerTouchpointFact,
    DataScopeMapping,
    EvidenceSnapshot,
    EvidenceSnapshotItem,
    SyncRun,
)
from zhixing_api.main import create_app


def make_settings(tmp_path: Path, *, ai_enabled: bool = False) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://test",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'customer_operations_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
        ai_enabled=ai_enabled,
        ai_api_key="test-key" if ai_enabled else "",
        ai_model="customer-operation-test-model",
    )


def seed_customer_facts(app: object) -> None:
    database = app.state.database  # type: ignore[attr-defined]
    now = datetime(2026, 8, 27, 12, tzinfo=UTC)
    with database.session() as session:
        session.add_all(
            [
                SyncRun(
                    id="sync_customer_ops_crm",
                    enterprise_id="ent_zhixing_demo",
                    external_system_id="source_mock_crm",
                    status="succeeded",
                    scenario="normal",
                    volume_profile="small",
                    records_read=3,
                    records_written=3,
                    warning=None,
                    error=None,
                    started_at=now,
                    finished_at=now,
                ),
                SyncRun(
                    id="sync_customer_ops_erp",
                    enterprise_id="ent_zhixing_demo",
                    external_system_id="source_mock_commerce",
                    status="succeeded",
                    scenario="normal",
                    volume_profile="small",
                    records_read=3,
                    records_written=3,
                    warning=None,
                    error=None,
                    started_at=now,
                    finished_at=now,
                ),
                DataScopeMapping(
                    id="scope_customer_ops_store",
                    enterprise_id="ent_zhixing_demo",
                    external_system_id="source_mock_crm",
                    sync_run_id="sync_customer_ops_crm",
                    scope_type="store",
                    scope_key="store-flagship",
                    external_scope_key="TM-001",
                    label="天猫旗舰店",
                    status="active",
                    attributes={"channel": "tmall"},
                    source_schema_version="CRM-TEST",
                    mapping_version="1.0.0",
                    created_at=now,
                    updated_at=now,
                ),
                CustomerProfile(
                    id="customer_ops_profile_001",
                    enterprise_id="ent_zhixing_demo",
                    external_system_id="source_mock_crm",
                    sync_run_id="sync_customer_ops_crm",
                    customer_key="CUS-OPS-001",
                    display_name="高价值流失预警客户",
                    home_store_key="TM-001",
                    member_level="gold",
                    lifecycle_stage="at_risk",
                    status="active",
                    province="浙江",
                    acquisition_channel="tmall",
                    registered_at=now,
                    last_active_at=now,
                    member_points=1600,
                    growth_value=4600,
                    churn_risk_score=0.86,
                    preferred_category="护肤",
                    consent_status="granted",
                    tags=["高价值", "流失预警"],
                    created_at=now,
                    updated_at=now,
                ),
                CustomerProfile(
                    id="customer_ops_profile_002",
                    enterprise_id="ent_zhixing_demo",
                    external_system_id="source_mock_crm",
                    sync_run_id="sync_customer_ops_crm",
                    customer_key="CUS-OPS-OTHER",
                    display_name="其他门店客户",
                    home_store_key="JD-002",
                    member_level="standard",
                    lifecycle_stage="new",
                    status="active",
                    province="江苏",
                    acquisition_channel="jd",
                    registered_at=now,
                    last_active_at=now,
                    member_points=100,
                    growth_value=200,
                    churn_risk_score=0.2,
                    preferred_category="食品",
                    consent_status="revoked",
                    tags=["新客"],
                    created_at=now,
                    updated_at=now,
                ),
                CustomerTouchpointFact(
                    id="customer_ops_touchpoint_001",
                    enterprise_id="ent_zhixing_demo",
                    external_system_id="source_mock_crm",
                    sync_run_id="sync_customer_ops_crm",
                    touchpoint_key="EVT-OPS-001",
                    customer_key="CUS-OPS-001",
                    store_key="TM-001",
                    touchpoint_type="campaign_click",
                    channel="tmall",
                    occurred_at=now,
                    campaign_key="CAM-OPS-001",
                    value_fen=0,
                    properties={"product_key": "SPU-OPS-001"},
                    created_at=now,
                    updated_at=now,
                ),
                CommerceOrderFact(
                    id="customer_ops_order_001",
                    enterprise_id="ent_zhixing_demo",
                    external_system_id="source_mock_commerce",
                    sync_run_id="sync_customer_ops_erp",
                    order_key="ORD-OPS-001",
                    store_key="TM-001",
                    customer_key="CUS-OPS-001",
                    channel="tmall",
                    status="completed",
                    business_date=date(2026, 8, 25),
                    paid_at=now,
                    shipped_at=now,
                    paid_amount_fen=120_000,
                    item_amount_fen=120_000,
                    discount_amount_fen=0,
                    freight_amount_fen=0,
                    cost_amount_fen=70_000,
                    item_count=2,
                    province="浙江",
                    created_at=now,
                    updated_at=now,
                ),
                CommerceRefundFact(
                    id="customer_ops_refund_001",
                    enterprise_id="ent_zhixing_demo",
                    external_system_id="source_mock_commerce",
                    sync_run_id="sync_customer_ops_erp",
                    refund_key="REF-OPS-001",
                    order_key="ORD-OPS-001",
                    line_key="LINE-OPS-001",
                    store_key="TM-001",
                    customer_key="CUS-OPS-001",
                    sku_key="SKU-OPS-001",
                    reason_category="商品质量",
                    status="completed",
                    requested_at=now,
                    completed_at=now,
                    refund_amount_fen=30_000,
                    quantity=1,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()


@pytest.mark.anyio
async def test_customer_operation_fallback_freezes_evidence_and_is_idempotent(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    seed_customer_facts(app)
    headers = {"X-Zhixing-Demo-Actor": "ceo"}
    payload = {
        "scope_key": "enterprise",
        "customer_key": "CUS-OPS-001",
        "objective": "提升该客户未来三十天复购概率，并降低流失风险",
        "client_request_key": "customer-operation-fallback-001",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        empty = await client.get(
            "/api/v1/customer-operations/studio",
            params={"scope_key": "enterprise", "customer_key": "CUS-OPS-001"},
            headers=headers,
        )
        created = await client.post(
            "/api/v1/customer-operations/plans", json=payload, headers=headers
        )
        repeated = await client.post(
            "/api/v1/customer-operations/plans", json=payload, headers=headers
        )
        conflict = await client.post(
            "/api/v1/customer-operations/plans",
            json={**payload, "objective": "仅分析客户服务风险，不制定复购方案"},
            headers=headers,
        )

    assert empty.status_code == 200
    assert empty.json()["runs"] == []
    assert empty.json()["can_run"] is True
    assert created.status_code == 200
    run = created.json()["run"]
    assert created.json()["idempotent"] is False
    assert run["execution_mode"] == "rule-fallback"
    assert run["risk_level"] == "high"
    assert run["evidence_snapshot"]["item_count"] == len(run["evidence"])
    assert len(run["evidence"]) >= 5
    allowed_refs = {item["evidence_ref"] for item in run["evidence"]}
    assert all(set(item["evidence_refs"]) <= allowed_refs for item in run["result"]["steps"])
    assert all(item["requires_human_approval"] for item in run["result"]["steps"])
    assert all(not item["external_write_allowed"] for item in run["result"]["steps"])
    assert run["result"]["prohibited_actions"]
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["run"]["id"] == run["id"]
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "customer_operation.idempotency_conflict"
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(CustomerOperationRun.id))) == 1
        assert session.scalar(select(func.count(EvidenceSnapshot.id))) == 1
        assert session.scalar(select(func.count(EvidenceSnapshotItem.id))) == len(run["evidence"])


@pytest.mark.anyio
async def test_customer_operation_uses_model_and_enforces_permission_and_scope(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path, ai_enabled=True))
    seed_customer_facts(app)

    class StubProvider:
        async def generate(self, *_args: object, **_kwargs: object) -> AICompletion:
            return AICompletion(
                payload={
                    "headline": "高价值客户流失风险需要先核验退款体验",
                    "summary": "客户仍有互动，但退款与高流失评分需要人工复核。",
                    "diagnoses": [
                        {
                            "kind": "risk",
                            "severity": "high",
                            "text": "退款事实与流失评分同时指向体验风险。",
                            "evidence_refs": ["E1", "E2", "E4"],
                        }
                    ],
                    "steps": [
                        {
                            "title": "复核退款与服务记录",
                            "action": "由客服主管核验退款原因与历史服务记录，形成内部处理建议。",
                            "owner_role": "客服主管",
                            "priority": "high",
                            "action_type": "manual_review",
                            "evidence_refs": ["E2", "E4"],
                            "success_metric": "退款体验问题完成归因",
                            "stop_condition": "证据不足或客户同意状态变化时停止",
                        }
                    ],
                    "unknowns": ["尚缺完整历史服务工单。"],
                    "confidence": "medium",
                },
                input_tokens=360,
                output_tokens=150,
            )

    app.state.ai_provider = StubProvider()
    manager = {"X-Zhixing-Demo-Actor": "manager"}
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    admin = {"X-Zhixing-Demo-Actor": "admin"}
    finance = {"X-Zhixing-Demo-Actor": "finance"}
    request_payload = {
        "scope_key": "store-flagship",
        "customer_key": "CUS-OPS-001",
        "objective": "降低高价值客户的流失概率并形成内部服务复核方案",
        "client_request_key": "customer-operation-model-001",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/customer-operations/plans", json=request_payload, headers=manager
        )
        employee_read = await client.get(
            "/api/v1/customer-operations/studio",
            params={"scope_key": "store-flagship", "customer_key": "CUS-OPS-001"},
            headers=employee,
        )
        employee_run = await client.post(
            "/api/v1/customer-operations/plans",
            json={**request_payload, "client_request_key": "customer-operation-denied-001"},
            headers=employee,
        )
        manager_enterprise = await client.post(
            "/api/v1/customer-operations/plans",
            json={
                **request_payload,
                "scope_key": "enterprise",
                "client_request_key": "customer-operation-enterprise-denied-001",
            },
            headers=manager,
        )
        wrong_customer = await client.get(
            "/api/v1/customer-operations/studio",
            params={"scope_key": "store-flagship", "customer_key": "CUS-OPS-OTHER"},
            headers=employee,
        )
        ai_operations = await client.get("/api/v1/ai-operations/overview", headers=admin)
        operation_id = created.json()["run"]["id"]
        proposal_payload = {
            "step_indexes": [0],
            "due_hint": "未来 7 天内完成",
            "idempotency_key": "customer-operation-action-001",
        }
        proposed = await client.post(
            f"/api/v1/customer-operations/plans/{operation_id}/action-proposals",
            json=proposal_payload,
            headers=manager,
        )
        repeated_proposal = await client.post(
            f"/api/v1/customer-operations/plans/{operation_id}/action-proposals",
            json=proposal_payload,
            headers=manager,
        )
        changed_due = await client.post(
            f"/api/v1/customer-operations/plans/{operation_id}/action-proposals",
            json={**proposal_payload, "due_hint": "未来 3 天内完成"},
            headers=manager,
        )
        employee_proposal = await client.post(
            f"/api/v1/customer-operations/plans/{operation_id}/action-proposals",
            json={**proposal_payload, "idempotency_key": "customer-operation-action-employee"},
            headers=employee,
        )
        employee_actions = await client.get(
            "/api/v1/action-proposals",
            headers=employee,
        )
        action_listing = await client.get(
            "/api/v1/action-proposals",
            headers=manager,
        )
        proposal_key = proposed.json()["items"][0]["key"]
        self_approval = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers=manager,
            json={
                "decision": "approve",
                "comment": "发起人不能审批自己的客户运营行动。",
                "idempotency_key": "customer-operation-self-approval",
            },
        )
        approved = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers=finance,
            json={
                "decision": "approve",
                "comment": "批准登记内部复核任务，不触发客户触达。",
                "idempotency_key": "customer-operation-finance-approval",
            },
        )
        refreshed_studio = await client.get(
            "/api/v1/customer-operations/studio",
            params={"scope_key": "store-flagship", "customer_key": "CUS-OPS-001"},
            headers=manager,
        )

    assert created.status_code == 200
    run = created.json()["run"]
    assert run["execution_mode"] == "model"
    assert run["provider"] == "openai-compatible-responses"
    assert run["input_tokens"] == 360
    assert run["output_tokens"] == 150
    assert run["result"]["steps"][0]["requires_human_approval"] is True
    assert run["result"]["steps"][0]["external_write_allowed"] is False
    assert employee_read.status_code == 200
    assert employee_read.json()["can_run"] is False
    assert employee_run.status_code == 403
    assert employee_run.json()["error"]["code"] == "authorization.permission_denied"
    assert manager_enterprise.status_code == 403
    assert manager_enterprise.json()["error"]["code"] == "authorization.scope_denied"
    assert wrong_customer.status_code == 404
    assert wrong_customer.json()["error"]["code"] == "customer.profile_not_found"
    assert ai_operations.status_code == 200
    latest = ai_operations.json()["latest_runs"]
    assert any(item["category"] == "customer-operation" for item in latest)
    assert proposed.status_code == 200
    proposal_response = proposed.json()
    assert proposal_response["created_count"] == 1
    assert proposal_response["idempotent"] is False
    proposal = proposal_response["items"][0]
    assert proposal["source_type"] == "customer-operation"
    assert proposal["source_key"] == run["id"]
    assert proposal["scope_type"] == "store"
    assert proposal["scope_key"] == "store-flagship"
    assert proposal["meeting_key"] is None
    assert proposal["decision_package_id"] is None
    assert proposal["customer_operation_run_id"] == run["id"]
    assert proposal["evidence_snapshot_id"] == run["evidence_snapshot"]["id"]
    assert proposal["source_route"].endswith("/store-flagship/CUS-OPS-001")
    assert repeated_proposal.status_code == 200
    assert repeated_proposal.json()["created_count"] == 0
    assert repeated_proposal.json()["idempotent"] is True
    assert changed_due.status_code == 409
    assert changed_due.json()["error"]["code"] == (
        "action.customer_operation_step_already_proposed"
    )
    assert employee_proposal.status_code == 403
    assert employee_actions.status_code == 200
    assert employee_actions.json()["stats"]["total"] == 0
    assert action_listing.status_code == 200
    assert action_listing.json()["stats"]["total"] == 1
    assert self_approval.status_code == 403
    assert self_approval.json()["error"]["code"] == "authorization.separation_of_duties"
    assert approved.status_code == 200
    assert approved.json()["item"]["status"] == "approved"
    assert approved.json()["item"]["execution"]["external_write"] is False
    assert refreshed_studio.status_code == 200
    assert refreshed_studio.json()["can_propose"] is True
    assert refreshed_studio.json()["runs"][0]["action_proposals"] == [
        {
            "step_index": 0,
            "proposal_key": proposal_key,
            "status": "approved",
        }
    ]
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(ActionProposal.id))) == 1
        assert session.scalar(select(func.count(ActionApprovalEvent.id))) == 1
        assert session.scalar(select(func.count(ActionExecution.id))) == 1
