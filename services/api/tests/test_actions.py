from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    ActionApprovalEvent,
    ActionExecution,
    ActionProposal,
    ActionWorkEvent,
    ActionWorkItem,
    BusinessAnalysisRun,
    EvidenceSnapshot,
    MeetingDecisionConfirmation,
    ScopeGrant,
)
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'actions_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


async def run_fallback_meeting(client: AsyncClient) -> dict[str, object]:
    response = await client.post(
        "/api/v1/decision-meetings/mtg-budget-20260825/run",
        headers={"X-Zhixing-Demo-Actor": "ceo"},
        json={"refresh_evidence": True},
    )
    assert response.status_code == 200
    return response.json()


@pytest.mark.anyio
async def test_human_confirmation_creates_idempotent_action_proposals(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        meeting_run = await run_fallback_meeting(client)
        action_count = len(meeting_run["detail"]["decision_package"]["actions"])

        unauthenticated = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/confirm",
            json={"comment": "确认受控试验并生成行动。"},
        )
        employee = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/confirm",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json={"comment": "尝试确认。"},
        )
        manager = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/confirm",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json={"comment": "尝试确认。"},
        )
        confirmed = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/confirm",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"comment": "确认按停止条件推进，所有动作先进入内部审批。"},
        )
        repeated = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/confirm",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"comment": "重复提交不得新建记录。"},
        )
        other_confirmer = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/confirm",
            headers={"X-Zhixing-Demo-Actor": "finance"},
            json={"comment": "不同确认人不得覆盖。"},
        )
        rerun = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/run",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"refresh_evidence": False},
        )

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "auth.development_actor_required"
    assert employee.status_code == 403
    assert manager.status_code == 403
    assert confirmed.status_code == 200
    confirmed_payload = confirmed.json()
    assert confirmed_payload["created_action_count"] == action_count
    assert confirmed_payload["detail"]["meeting"]["protocol_status"] == "actions_created"
    assert confirmed_payload["detail"]["decision_package"]["status"] == "confirmed"
    assert confirmed_payload["detail"]["confirmation"]["confirmed_by_name"] == "林知远 / CEO"
    assert len(confirmed_payload["detail"]["action_proposals"]) == action_count
    assert {item["status"] for item in confirmed_payload["detail"]["action_proposals"]} == {
        "pending_approval"
    }
    assert repeated.status_code == 200
    assert repeated.json()["created_action_count"] == 0
    assert other_confirmer.status_code == 409
    assert rerun.status_code == 409
    assert rerun.json()["error"]["code"] == "meeting.confirmed_decision_locked"

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(MeetingDecisionConfirmation.id))) == 1
        confirmation = session.scalar(select(MeetingDecisionConfirmation))
        assert confirmation.actor_context["scope_context"]["schema_version"] == 2
        assert session.scalar(select(func.count(ActionProposal.id))) == action_count


@pytest.mark.anyio
async def test_action_approval_enforces_permissions_duties_and_idempotency(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await run_fallback_meeting(client)
        confirmation = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/confirm",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"comment": "确认生成内部行动提案。"},
        )
        proposal_key = confirmation.json()["detail"]["action_proposals"][0]["key"]
        request_payload = {
            "decision": "approve",
            "comment": "批准登记内部任务台账，暂不调用外部系统。",
            "idempotency_key": f"approval:{proposal_key}:v1",
        }

        employee = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers={"X-Zhixing-Demo-Actor": "employee"},
            json=request_payload,
        )
        ceo = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json=request_payload,
        )
        approved = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json=request_payload,
        )
        repeated = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json=request_payload,
        )
        changed = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json={
                "decision": "reject",
                "comment": "不能覆盖既有结论。",
                "idempotency_key": f"approval:{proposal_key}:v2",
            },
        )
        listing = await client.get(
            "/api/v1/action-proposals",
            headers={"X-Zhixing-Demo-Actor": "manager"},
        )

    assert employee.status_code == 403
    assert ceo.status_code == 403
    assert approved.status_code == 200
    item = approved.json()["item"]
    assert item["status"] == "approved"
    assert item["approved_by_name"] == "周岚 / 运营经理"
    assert item["execution"]["status"] == "recorded"
    assert item["execution"]["external_write"] is False
    assert repeated.status_code == 200
    assert changed.status_code == 409
    assert listing.status_code == 200
    assert listing.json()["stats"]["approved"] == 1
    assert listing.json()["stats"]["recorded_executions"] == 1

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(ActionApprovalEvent.id))) == 1
        approval = session.scalar(select(ActionApprovalEvent))
        assert approval.actor_context["scope_context"]["schema_version"] == 2
        created = session.scalar(select(ActionWorkEvent).where(
            ActionWorkEvent.event_type == "created"))
        assert created.actor_snapshot["scope_context"] == approval.actor_context["scope_context"]
        assert session.scalar(select(func.count(ActionExecution.id))) == 1


@pytest.mark.anyio
async def test_action_approval_requires_separation_from_finance_confirmer(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await run_fallback_meeting(client)
        confirmation = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/confirm",
            headers={"X-Zhixing-Demo-Actor": "finance"},
            json={"comment": "财务负责人确认。"},
        )
        proposal_key = confirmation.json()["detail"]["action_proposals"][0]["key"]
        response = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers={"X-Zhixing-Demo-Actor": "finance"},
            json={
                "decision": "approve",
                "comment": "同一人不得批准。",
                "idempotency_key": f"approval:{proposal_key}:finance",
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "authorization.separation_of_duties"


@pytest.mark.anyio
async def test_action_approval_rejects_actor_outside_object_scope(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await run_fallback_meeting(client)
        confirmation = await client.post(
            "/api/v1/decision-meetings/mtg-budget-20260825/confirm",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
            json={"comment": "确认生成内部行动提案。"},
        )
        proposal_key = confirmation.json()["detail"]["action_proposals"][0]["key"]
        with app.state.database.session() as session:
            scope = session.get(ScopeGrant, "scope_manager_object")
            assert scope is not None
            scope.scope_ids = ["mtg-another-department"]
            session.commit()
        response = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers={"X-Zhixing-Demo-Actor": "manager"},
            json={
                "decision": "approve",
                "comment": "不应越过对象范围。",
                "idempotency_key": f"approval:{proposal_key}:scope-denied",
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "authorization.scope_denied"


@pytest.mark.anyio
async def test_analysis_recommendation_becomes_scoped_employee_work_item(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    now = datetime.now(UTC)
    analysis_id = "business_analysis_workflow_001"
    with app.state.database.session() as session:
        session.add(
            EvidenceSnapshot(
                id="evidence_analysis_workflow_001",
                enterprise_id="ent_zhixing_demo",
                snapshot_key="analysis-workflow-001",
                purpose="business-analysis",
                query="旗舰店经营诊断",
                content_hash="a" * 64,
                item_count=2,
                frozen_at=now,
            )
        )
        session.add(
            BusinessAnalysisRun(
                id=analysis_id,
                enterprise_id="ent_zhixing_demo",
                analysis_type="store-review",
                scope_type="store",
                scope_key="store-flagship",
                scope_label="旗舰店",
                window_days=30,
                status="completed",
                risk_level="high",
                provider="test-provider",
                model="test-model",
                execution_mode="model",
                fallback_reason=None,
                evidence_snapshot_id="evidence_analysis_workflow_001",
                result={
                    "headline": "旗舰店退款与库存风险需要协同处理",
                    "summary": "冻结证据显示两项风险需要人工推进。",
                    "confidence": "high",
                    "metric_snapshot": [],
                    "commerce_fact_snapshot": [],
                    "findings": [],
                    "recommendations": [
                        {
                            "title": "复核高退款 SKU",
                            "action": "核对退款原因并形成商品处置建议。",
                            "owner_role": "运营专员",
                            "priority": "high",
                            "evidence_refs": ["E1", "E2"],
                            "success_metric": "退款原因完成归类",
                            "stop_condition": "证据不足时暂停商品调整",
                        }
                    ],
                    "unknowns": [],
                },
                initiated_by_principal_id="principal-ops-manager-zhou",
                actor_snapshot={},
                idempotency_key="analysis-workflow-001",
                request_id="request-analysis-workflow-001",
                run_id="run-analysis-workflow-001",
                created_at=now,
                completed_at=now,
            )
        )
        session.commit()

    manager = {"X-Zhixing-Demo-Actor": "manager"}
    finance = {"X-Zhixing-Demo-Actor": "finance"}
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    ceo = {"X-Zhixing-Demo-Actor": "ceo"}
    proposal_request = {
        "recommendation_indexes": [0],
        "due_hint": "今天闭店前",
        "idempotency_key": "analysis-actions-workflow-001",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        employee_denied = await client.post(
            f"/api/v1/analysis/runs/{analysis_id}/action-proposals",
            headers=employee,
            json=proposal_request,
        )
        created = await client.post(
            f"/api/v1/analysis/runs/{analysis_id}/action-proposals",
            headers=manager,
            json=proposal_request,
        )
        repeated = await client.post(
            f"/api/v1/analysis/runs/{analysis_id}/action-proposals",
            headers=manager,
            json=proposal_request,
        )
        proposal_key = created.json()["items"][0]["key"]
        approved = await client.post(
            f"/api/v1/action-proposals/{proposal_key}/decision",
            headers=finance,
            json={
                "decision": "approve",
                "comment": "批准进入旗舰店内部运营工作台。",
                "idempotency_key": "approve-analysis-workflow-001",
            },
        )
        employee_board = await client.get("/api/v1/action-work-items", headers=employee)
        work_item = employee_board.json()["items"][0]
        work_key = work_item["key"]
        claimed = await client.post(
            f"/api/v1/action-work-items/{work_key}/events",
            headers=employee,
            json={
                "action": "claim",
                "comment": "领取旗舰店退款复核任务。",
                "evidence_refs": [],
                "expected_version": 1,
                "idempotency_key": "work-claim-analysis-001",
            },
        )
        repeated_claim = await client.post(
            f"/api/v1/action-work-items/{work_key}/events",
            headers=employee,
            json={
                "action": "claim",
                "comment": "重复领取不得新增事件。",
                "evidence_refs": [],
                "expected_version": 1,
                "idempotency_key": "work-claim-analysis-001",
            },
        )
        stale_start = await client.post(
            f"/api/v1/action-work-items/{work_key}/events",
            headers=employee,
            json={
                "action": "start",
                "comment": "使用旧版本启动。",
                "evidence_refs": [],
                "expected_version": 1,
                "idempotency_key": "work-start-analysis-stale-001",
            },
        )
        ceo_denied = await client.post(
            f"/api/v1/action-work-items/{work_key}/events",
            headers=ceo,
            json={
                "action": "start",
                "comment": "只读负责人不能代替员工更新。",
                "evidence_refs": [],
                "expected_version": 2,
                "idempotency_key": "work-start-analysis-ceo-001",
            },
        )
        started = await client.post(
            f"/api/v1/action-work-items/{work_key}/events",
            headers=employee,
            json={
                "action": "start",
                "comment": "开始核对退款原因。",
                "evidence_refs": ["E1"],
                "expected_version": 2,
                "idempotency_key": "work-start-analysis-001",
            },
        )
        completed = await client.post(
            f"/api/v1/action-work-items/{work_key}/events",
            headers=employee,
            json={
                "action": "complete",
                "comment": "已核对退款原因并形成内部处置建议。",
                "evidence_refs": ["E1", "E2"],
                "expected_version": 3,
                "idempotency_key": "work-complete-analysis-001",
            },
        )

    assert employee_denied.status_code == 403
    assert created.status_code == 200
    assert created.json()["created_count"] == 1
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert approved.status_code == 200
    assert approved.json()["item"]["work_item"]["status"] == "ready"
    assert employee_board.status_code == 200
    assert employee_board.json()["stats"]["ready"] == 1
    assert work_item["source_type"] == "business-analysis"
    assert work_item["available_actions"] == ["claim"]
    assert claimed.status_code == 200
    assert claimed.json()["item"]["status"] == "claimed"
    assert repeated_claim.status_code == 200
    assert repeated_claim.json()["idempotent"] is True
    assert stale_start.status_code == 409
    assert stale_start.json()["error"]["code"] == "action.work.version_conflict"
    assert ceo_denied.status_code == 403
    assert started.status_code == 200
    assert started.json()["item"]["status"] == "in_progress"
    assert completed.status_code == 200
    assert completed.json()["item"]["status"] == "completed"
    assert completed.json()["item"]["result_evidence_refs"] == ["E1", "E2"]
    assert len(completed.json()["item"]["events"]) == 4

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(ActionWorkItem.id))) == 1
        assert session.scalar(select(func.count(ActionWorkEvent.id))) == 4
