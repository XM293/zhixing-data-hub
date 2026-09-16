from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.config import Settings
from zhixing_api.data_models import AgentFeedbackEvent, AgentRun, HumanHandoffCase
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'agent_feedback_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


@pytest.mark.anyio
async def test_answer_feedback_creates_owned_handoff_case_idempotently(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    finance = {"X-Zhixing-Demo-Actor": "finance"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        answer = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers=employee,
            json={"question": "9 月退款率如何考核？"},
        )
        run_id = answer.json()["run_id"]
        helpful = await client.post(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=employee,
            json={
                "kind": "helpful",
                "message": "引用清楚",
                "priority": "normal",
                "client_request_key": f"{run_id}-helpful-v1",
            },
        )
        correction = await client.post(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=employee,
            json={
                "kind": "inaccurate",
                "message": "没有明确区分当前制度与尚未生效的制度。",
                "expected_answer": "应明确当前仍按现行制度执行，并标明新制度生效日期。",
                "priority": "high",
                "client_request_key": f"{run_id}-correction-v1",
            },
        )
        repeated = await client.post(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=employee,
            json={
                "kind": "inaccurate",
                "message": "没有明确区分当前制度与尚未生效的制度。",
                "expected_answer": "应明确当前仍按现行制度执行，并标明新制度生效日期。",
                "priority": "high",
                "client_request_key": f"{run_id}-correction-v1",
            },
        )
        own_status = await client.get(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=employee,
        )
        other_actor = await client.get(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=finance,
        )

    assert answer.status_code == 200
    assert helpful.status_code == 200
    assert helpful.json()["handoff_case"] is None
    assert correction.status_code == 200
    assert correction.json()["idempotent"] is False
    assert correction.json()["handoff_case"]["status"] == "open"
    assert correction.json()["handoff_case"]["priority"] == "high"
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["feedback"]["id"] == correction.json()["feedback"]["id"]
    assert own_status.status_code == 200
    assert len(own_status.json()["feedback_events"]) == 2
    assert other_actor.status_code == 403
    assert other_actor.json()["error"]["code"] == "agent_feedback.run_not_owned"

    with app.state.database.session() as session:
        run = session.get(AgentRun, run_id)
        assert run is not None
        assert run.actor_principal_id == "principal-employee-demo"
        assert session.scalar(select(func.count(AgentFeedbackEvent.id))) == 2
        assert session.scalar(select(func.count(HumanHandoffCase.id))) == 1


@pytest.mark.anyio
async def test_feedback_queue_requires_review_permission_and_keeps_resolution_ledger(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    manager = {"X-Zhixing-Demo-Actor": "manager"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        answer = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers=employee,
            json={"question": "库存低于多少天需要停止扩量？"},
        )
        run_id = answer.json()["run_id"]
        submitted = await client.post(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=employee,
            json={
                "kind": "handoff",
                "message": "这个问题会影响今天的投放，请运营负责人确认。",
                "priority": "urgent",
                "client_request_key": f"{run_id}-handoff-v1",
            },
        )
        case_id = submitted.json()["handoff_case"]["id"]
        employee_queue = await client.get("/api/v1/agent-feedback/studio", headers=employee)
        manager_queue = await client.get("/api/v1/agent-feedback/studio", headers=manager)
        employee_resolve = await client.post(
            f"/api/v1/agent-feedback/cases/{case_id}/actions",
            headers=employee,
            json={
                "action": "resolve",
                "message": "尝试越权处理",
                "resolution_type": "corrected_answer",
                "resolution_summary": "不应成功",
                "client_request_key": f"{case_id}-employee-resolve",
            },
        )
        assigned = await client.post(
            f"/api/v1/agent-feedback/cases/{case_id}/actions",
            headers=manager,
            json={
                "action": "assign_to_me",
                "message": "运营负责人接管核验库存口径。",
                "client_request_key": f"{case_id}-assign-manager",
            },
        )
        resolved = await client.post(
            f"/api/v1/agent-feedback/cases/{case_id}/actions",
            headers=manager,
            json={
                "action": "resolve",
                "message": "已核对安全库存制度和最新库存数据。",
                "resolution_type": "corrected_answer",
                "resolution_summary": "可售天数低于 10 天暂停扩量，低于 7 天进入补货升级。",
                "client_request_key": f"{case_id}-resolve-manager",
            },
        )
        repeated_resolve = await client.post(
            f"/api/v1/agent-feedback/cases/{case_id}/actions",
            headers=manager,
            json={
                "action": "resolve",
                "message": "已核对安全库存制度和最新库存数据。",
                "resolution_type": "corrected_answer",
                "resolution_summary": "可售天数低于 10 天暂停扩量，低于 7 天进入补货升级。",
                "client_request_key": f"{case_id}-resolve-manager",
            },
        )
        final_queue = await client.get("/api/v1/agent-feedback/studio", headers=manager)
        employee_status = await client.get(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=employee,
        )
        employee_feedback = await client.get(
            "/api/v1/agent-feedback/mine",
            headers=employee,
        )

    assert submitted.status_code == 200
    assert employee_queue.status_code == 403
    assert manager_queue.status_code == 200
    assert manager_queue.json()["stats"]["urgent_count"] == 1
    assert employee_resolve.status_code == 403
    assert assigned.status_code == 200
    assert assigned.json()["handoff_case"]["status"] == "in_review"
    assert resolved.status_code == 200
    assert resolved.json()["handoff_case"]["status"] == "resolved"
    assert resolved.json()["handoff_case"]["resolution_type"] == "corrected_answer"
    assert repeated_resolve.status_code == 200
    assert repeated_resolve.json()["idempotent"] is True
    assert final_queue.json()["stats"]["resolved_count"] == 1
    assert len(final_queue.json()["cases"][0]["events"]) == 3
    assert employee_status.json()["handoff_case"]["resolution_summary"].startswith(
        "可售天数低于 10 天"
    )
    assert employee_feedback.status_code == 200
    assert employee_feedback.json()["stats"]["resolved_count"] == 1
    assert employee_feedback.json()["cases"][0]["agent_run_id"] == run_id
