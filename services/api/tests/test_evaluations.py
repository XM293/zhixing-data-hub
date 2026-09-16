from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    AgentRun,
    EvaluationCase,
    EvaluationRun,
    EvaluationRunItem,
    EvaluationSuite,
)
from zhixing_api.main import create_app


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'evaluation_runner_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
    )


@pytest.mark.anyio
async def test_evaluation_studio_and_batch_runner_are_authorized_and_versioned(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    ceo = {"X-Zhixing-Demo-Actor": "ceo"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/api/v1/evaluations/studio")
        denied_read = await client.get("/api/v1/evaluations/studio", headers=employee)
        studio = await client.get("/api/v1/evaluations/studio", headers=ceo)
        denied_run = await client.post(
            "/api/v1/evaluation-suites/m1-role-twin-smoke/runs",
            headers=employee,
            json={"client_request_key": "employee-eval-denied-001", "case_keys": []},
        )
        first = await client.post(
            "/api/v1/evaluation-suites/m1-role-twin-smoke/runs",
            headers=ceo,
            json={"client_request_key": "m1-smoke-run-001", "case_keys": []},
        )
        repeated = await client.post(
            "/api/v1/evaluation-suites/m1-role-twin-smoke/runs",
            headers=ceo,
            json={"client_request_key": "m1-smoke-run-001", "case_keys": []},
        )
        conflicting_suite = await client.post(
            "/api/v1/evaluation-suites/another-suite/runs",
            headers=ceo,
            json={"client_request_key": "m1-smoke-run-001", "case_keys": []},
        )
        second = await client.post(
            "/api/v1/evaluation-suites/m1-role-twin-smoke/runs",
            headers=ceo,
            json={"client_request_key": "m1-smoke-run-002", "case_keys": []},
        )

    assert missing.status_code == 401
    assert denied_read.status_code == 403
    assert studio.status_code == 200
    assert studio.json()["stats"]["suite_count"] == 1
    assert studio.json()["stats"]["case_count"] == 6
    assert denied_run.status_code == 403
    assert first.status_code == 200
    assert first.json()["idempotent"] is False
    first_run = first.json()["run"]
    assert first_run["status"] == "completed"
    assert first_run["total_count"] == 6
    assert first_run["passed_count"] == 5
    assert first_run["failed_count"] == 0
    assert first_run["review_required_count"] == 1
    assert first_run["error_count"] == 0
    assert first_run["pass_rate"] == pytest.approx(5 / 6, abs=0.001)
    assert len(first_run["items"]) == 6
    assert all(item["case_snapshot"] for item in first_run["items"])
    assert all(item["actor_snapshot"] for item in first_run["items"])
    denied_item = next(
        item for item in first_run["items"] if item["case_key"] == "eval-scope-denied"
    )
    assert denied_item["agent_run_id"] is None
    assert denied_item["outcome"] == "passed"
    assert denied_item["observed_error_code"] == "authorization.scope_denied"
    assert repeated.status_code == 200
    assert repeated.json()["idempotent"] is True
    assert repeated.json()["run"]["id"] == first_run["id"]
    assert conflicting_suite.status_code == 409
    assert conflicting_suite.json()["error"]["code"] == "evaluation.idempotency_conflict"
    assert second.status_code == 200
    assert second.json()["run"]["baseline_run_id"] == first_run["id"]
    assert second.json()["run"]["pass_rate_delta"] == pytest.approx(0.0)

    with app.state.database.session() as session:
        assert session.scalar(select(func.count(EvaluationSuite.id))) == 1
        assert session.scalar(select(func.count(EvaluationCase.id))) == 6
        assert session.scalar(select(func.count(EvaluationRun.id))) == 2
        assert session.scalar(select(func.count(EvaluationRunItem.id))) == 12
        assert session.scalar(
            select(func.count(AgentRun.id)).where(AgentRun.run_type == "answer")
        ) == 10
        actor_ids = set(
            session.scalars(
                select(EvaluationRunItem.actor_principal_id).where(
                    EvaluationRunItem.actor_principal_id.is_not(None)
                )
            )
        )
        assert {"principal-ceo-lin", "principal-employee-demo"}.issubset(actor_ids)


@pytest.mark.anyio
async def test_evaluation_runner_can_execute_a_selected_case_subset(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    ceo = {"X-Zhixing-Demo-Actor": "ceo"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/evaluation-suites/m1-role-twin-smoke/runs",
            headers=ceo,
            json={
                "client_request_key": "m1-smoke-subset-001",
                "case_keys": ["eval-policy-september", "eval-scope-denied"],
            },
        )

    assert response.status_code == 200
    run = response.json()["run"]
    assert run["total_count"] == 2
    assert run["passed_count"] == 2
    assert {item["case_key"] for item in run["items"]} == {
        "eval-policy-september",
        "eval-scope-denied",
    }
