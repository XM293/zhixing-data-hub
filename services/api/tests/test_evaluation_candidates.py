from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.config import Settings
from zhixing_api.data_models import EvaluationCandidate, EvaluationCase
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=(
            f"sqlite+pysqlite:///{(tmp_path / 'evaluation_candidate_test.db').as_posix()}"
        ),
        mock_commerce_url="http://127.0.0.1:8100",
    )


@pytest.mark.anyio
async def test_resolved_feedback_becomes_a_governed_evaluation_case(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    manager = {"X-Zhixing-Demo-Actor": "manager"}
    ceo = {"X-Zhixing-Demo-Actor": "ceo"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        answer = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers=employee,
            json={"question": "库存低于多少天必须暂停扩量？"},
        )
        run_id = answer.json()["run_id"]
        submitted = await client.post(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=employee,
            json={
                "kind": "inaccurate",
                "message": "回答没有给出已经确认的暂停阈值。",
                "expected_answer": "低于 10 天暂停扩量，低于 7 天升级补货。",
                "priority": "high",
                "client_request_key": f"{run_id}-candidate-feedback",
            },
        )
        case_id = submitted.json()["handoff_case"]["id"]
        resolved = await client.post(
            f"/api/v1/agent-feedback/cases/{case_id}/actions",
            headers=manager,
            json={
                "action": "resolve",
                "message": "已核对库存制度和运营停止条件。",
                "resolution_type": "corrected_answer",
                "resolution_summary": "低于 10 天暂停扩量，低于 7 天升级补货。",
                "client_request_key": f"{case_id}-candidate-resolution",
            },
        )
        studio = await client.get("/api/v1/evaluations/studio", headers=ceo)
        candidate = studio.json()["candidates"][0]
        manager_denied = await client.post(
            f"/api/v1/evaluation-candidates/{candidate['id']}/actions",
            headers=manager,
            json={
                "action": "accept",
                "reason": "经理不应能修改固定评测集。",
                "suite_key": "m1-role-twin-smoke",
                "client_request_key": f"{candidate['id']}-manager-denied",
            },
        )
        accepted = await client.post(
            f"/api/v1/evaluation-candidates/{candidate['id']}/actions",
            headers=ceo,
            json={
                "action": "accept",
                "reason": "纠正结论明确，纳入下一轮回归。",
                "suite_key": "m1-role-twin-smoke",
                "client_request_key": f"{candidate['id']}-accept-v1",
            },
        )
        repeated = await client.post(
            f"/api/v1/evaluation-candidates/{candidate['id']}/actions",
            headers=ceo,
            json={
                "action": "accept",
                "reason": "纠正结论明确，纳入下一轮回归。",
                "suite_key": "m1-role-twin-smoke",
                "client_request_key": f"{candidate['id']}-accept-v1",
            },
        )
        immutable = await client.post(
            f"/api/v1/evaluation-candidates/{candidate['id']}/actions",
            headers=ceo,
            json={
                "action": "reject",
                "reason": "尝试改写已经形成的审核结论。",
                "suite_key": "m1-role-twin-smoke",
                "client_request_key": f"{candidate['id']}-reject-v2",
            },
        )
        employee_status = await client.get(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=employee,
        )

    assert answer.status_code == 200
    assert submitted.status_code == 200
    assert resolved.status_code == 200
    assert resolved.json()["handoff_case"]["evaluation_candidate_status"] == "pending"
    assert studio.status_code == 200
    assert studio.json()["stats"]["candidate_count"] == 1
    assert studio.json()["stats"]["pending_candidate_count"] == 1
    assert candidate["expectations"]["reference_answer"].startswith("低于 10 天")
    assert manager_denied.status_code == 403
    assert accepted.status_code == 200
    assert accepted.json()["idempotent"] is False
    assert accepted.json()["candidate"]["status"] == "accepted"
    assert accepted.json()["studio"]["stats"]["case_count"] == 7
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert immutable.status_code == 409
    assert immutable.json()["error"]["code"] == "evaluation.candidate_already_reviewed"
    assert employee_status.status_code == 200
    assert employee_status.json()["handoff_case"]["evaluation_candidate_status"] == "accepted"

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(EvaluationCandidate.id))) == 1
        assert session.scalar(select(func.count(EvaluationCase.id))) == 7


@pytest.mark.anyio
async def test_no_issue_resolution_does_not_pollute_the_evaluation_set(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    manager = {"X-Zhixing-Demo-Actor": "manager"}
    ceo = {"X-Zhixing-Demo-Actor": "ceo"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        answer = await client.post(
            "/api/v1/twins/twin-ceo/answers",
            headers=employee,
            json={"question": "这条回答是否需要转人工复核？"},
        )
        run_id = answer.json()["run_id"]
        submitted = await client.post(
            f"/api/v1/agent-runs/{run_id}/feedback",
            headers=employee,
            json={
                "kind": "handoff",
                "message": "请负责人确认回答是否已经足够。",
                "priority": "normal",
                "client_request_key": f"{run_id}-no-issue-feedback",
            },
        )
        case_id = submitted.json()["handoff_case"]["id"]
        resolved = await client.post(
            f"/api/v1/agent-feedback/cases/{case_id}/actions",
            headers=manager,
            json={
                "action": "resolve",
                "message": "已复核，无需调整。",
                "resolution_type": "no_issue",
                "resolution_summary": "原回答符合当前制度和数据范围。",
                "client_request_key": f"{case_id}-no-issue-resolution",
            },
        )
        studio = await client.get("/api/v1/evaluations/studio", headers=ceo)

    assert resolved.status_code == 200
    assert resolved.json()["handoff_case"]["evaluation_candidate_id"] is None
    assert studio.status_code == 200
    assert studio.json()["stats"]["candidate_count"] == 0

