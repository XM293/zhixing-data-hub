from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    RoleTwinTestCase,
    RoleTwinTestReview,
    RoleTwinTestRun,
    RoleTwinVersion,
)
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'role_twin_review_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


@pytest.mark.anyio
async def test_role_twin_test_studio_is_database_backed_and_authorized(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/api/v1/role-twin-test-studio")
        denied = await client.get(
            "/api/v1/role-twin-test-studio",
            headers={"X-Zhixing-Demo-Actor": "employee"},
        )
        allowed = await client.get(
            "/api/v1/role-twin-test-studio",
            headers={"X-Zhixing-Demo-Actor": "ceo"},
        )

    assert missing.status_code == 401
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.permission_denied"
    assert allowed.status_code == 200
    payload = allowed.json()
    assert payload["schema_version"] == 1
    assert payload["stats"] == {
        "case_count": 6,
        "run_count": 0,
        "pending_review_count": 0,
        "reviewed_count": 0,
        "passed_count": 0,
        "pass_rate": None,
    }
    assert {item["key"] for item in payload["twins"]} == {
        "twin-ceo",
        "twin-ops",
        "twin-finance",
        "twin-service",
    }
    assert {item["category"] for item in payload["cases"]} >= {
        "knowledge",
        "data",
        "boundary",
        "style",
        "decision",
    }
    assert all(item["version_number"] == 1 for item in payload["cases"])
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(RoleTwinTestCase.id))) == 6


@pytest.mark.anyio
async def test_role_twin_test_run_and_review_preserve_versions_and_history(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    ceo = {"X-Zhixing-Demo-Actor": "ceo"}
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        run = await client.post(
            "/api/v1/role-twin-test-cases/case-policy-refund-september/runs",
            headers=ceo,
            json={"twin_key": "twin-ceo"},
        )
        employee_review = await client.post(
            f"/api/v1/role-twin-test-runs/{run.json()['run']['id']}/reviews",
            headers=employee,
            json={
                "decision": "pass",
                "evidence_grounding": 5,
                "boundary_adherence": 5,
                "voice_match": 4,
                "usefulness": 5,
                "notes": "员工不能替代角色负责人完成审核。",
            },
        )
        first_review = await client.post(
            f"/api/v1/role-twin-test-runs/{run.json()['run']['id']}/reviews",
            headers=ceo,
            json={
                "decision": "needs_revision",
                "evidence_grounding": 5,
                "boundary_adherence": 5,
                "voice_match": 3,
                "usefulness": 4,
                "notes": "证据正确，但表达还需要更明确地区分当前与未来版本。",
            },
        )
        second_review = await client.post(
            f"/api/v1/role-twin-test-runs/{run.json()['run']['id']}/reviews",
            headers=ceo,
            json={
                "decision": "pass",
                "evidence_grounding": 5,
                "boundary_adherence": 5,
                "voice_match": 4,
                "usefulness": 5,
                "notes": "复核通过；保留上一条审核事件。",
            },
        )
        studio = await client.get("/api/v1/role-twin-test-studio", headers=ceo)

    assert run.status_code == 200
    run_payload = run.json()["run"]
    assert run_payload["case_key"] == "case-policy-refund-september"
    assert run_payload["twin_key"] == "twin-ceo"
    assert run_payload["role_twin_version_number"] == 1
    assert run_payload["answer"]["summary"]
    assert run_payload["evidence_count"] >= 1
    assert employee_review.status_code == 403
    assert first_review.status_code == 200
    assert second_review.status_code == 200
    assert len(second_review.json()["run"]["reviews"]) == 2
    assert second_review.json()["run"]["latest_review"]["decision"] == "pass"
    assert studio.status_code == 200
    assert studio.json()["stats"] == {
        "case_count": 6,
        "run_count": 1,
        "pending_review_count": 0,
        "reviewed_count": 1,
        "passed_count": 1,
        "pass_rate": 1.0,
    }
    with app.state.database.session() as session:
        test_run = session.get(RoleTwinTestRun, run_payload["id"])
        assert test_run is not None
        agent_run = session.get(AgentRun, test_run.agent_run_id)
        role_version = session.get(RoleTwinVersion, test_run.role_twin_version_id)
        assert agent_run is not None
        assert role_version is not None
        assert agent_run.role_twin_version_id == test_run.role_twin_version_id
        assert role_version.version_number == 1
        assert session.scalar(select(func.count(RoleTwinTestReview.id))) == 2
