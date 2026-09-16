from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from zhixing_jobs import (
    JOB_EXECUTION_TOKEN_HEADER,
    WORKER_ID_HEADER,
    JobRecord,
    JobRepository,
)
from zhixing_jobs.models import BackgroundJob
from zhixing_observability import REQUEST_ID_HEADER, RUN_ID_HEADER

from zhixing_api.config import Settings
from zhixing_api.data_models import (
    ActionProposal,
    AuthorizationDecision,
    BusinessAnalysisRun,
    BusinessBrief,
    MetricSnapshot,
    RoleAssignment,
    ScopeGrant,
    StoreReviewPlan,
    StoreReviewScheduleRun,
)
from zhixing_api.main import create_app
from zhixing_api.review_schedule_service import calculate_next_run_at, dispatch_due_review_plans


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        timezone="Asia/Shanghai",
        cors_origins=("http://127.0.0.1:3000",),
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'review_schedule_test.db').as_posix()}",
        mock_commerce_url="http://127.0.0.1:8100",
        review_schedule_poll_seconds=3600,
    )


def seed_metric_series(app: object) -> None:
    database = app.state.database  # type: ignore[attr-defined]
    start = datetime(2026, 7, 29, tzinfo=UTC)
    values = {
        "gmv_today": (1_200_000.0, 18_000.0, "元", "今日成交"),
        "orders_today": (6_200.0, 80.0, "单", "支付订单"),
        "refund_rate": (5.6, 0.02, "%", "退款率"),
        "ad_roi": (2.8, 0.01, "x", "广告 ROI"),
    }
    with database.session() as session:
        for scope_key in ("enterprise", "store-flagship", "store-outlet"):
            for day in range(30):
                for metric_key, (base, step, unit, label) in values.items():
                    session.add(
                        MetricSnapshot(
                            id=f"scheduled_{scope_key}_{metric_key}_{day:02d}",
                            enterprise_id="ent_zhixing_demo",
                            source_system_id=None,
                            sync_run_id=None,
                            metric_key=metric_key,
                            label=label,
                            scope_key=scope_key,
                            value=base + step * day,
                            unit=unit,
                            change_rate=None,
                            as_of=start + timedelta(days=day),
                        )
                    )
        session.commit()


def worker_execution_headers(job: JobRecord, worker_id: str) -> dict[str, str]:
    assert job.execution_token
    return {
        WORKER_ID_HEADER: worker_id,
        JOB_EXECUTION_TOKEN_HEADER: job.execution_token,
        REQUEST_ID_HEADER: job.request_id,
        RUN_ID_HEADER: job.run_id,
    }


@pytest.mark.anyio
async def test_scheduled_review_runs_through_worker_and_creates_pending_actions(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    seed_metric_series(app)
    manager = {"X-Zhixing-Demo-Actor": "manager"}
    employee = {"X-Zhixing-Demo-Actor": "employee"}
    request_payload = {
        "name": "旗舰店每日风险巡检",
        "scope_key": "store-flagship",
        "window_days": 30,
        "timezone": "Asia/Shanghai",
        "local_time": "09:00",
        "weekdays": [1, 2, 3, 4, 5],
        "auto_propose_min_priority": "high",
        "client_request_key": "review-plan-flagship-001",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/analysis/review-plans", headers=manager, json=request_payload
        )
        repeated = await client.post(
            "/api/v1/analysis/review-plans", headers=manager, json=request_payload
        )
        employee_read = await client.get("/api/v1/analysis/review-plans", headers=employee)
        employee_create = await client.post(
            "/api/v1/analysis/review-plans",
            headers=employee,
            json={**request_payload, "client_request_key": "review-plan-employee-001"},
        )
        manager_enterprise = await client.post(
            "/api/v1/analysis/review-plans",
            headers=manager,
            json={
                **request_payload,
                "scope_key": "enterprise",
                "client_request_key": "review-plan-enterprise-denied-001",
            },
        )
        plan = created.json()["schedule"]["plans"][0]
        action_payload = {
            "action": "run_now",
            "expected_version": None,
            "idempotency_key": "review-run-now-001",
        }
        run_now = await client.post(
            f"/api/v1/analysis/review-plans/{plan['key']}/actions",
            headers=manager,
            json=action_payload,
        )
        repeated_run = await client.post(
            f"/api/v1/analysis/review-plans/{plan['key']}/actions",
            headers=manager,
            json=action_payload,
        )
        repository = JobRepository(app.state.database.engine)
        claimed = repository.claim("review-test-worker", lease_seconds=180)
        assert claimed is not None
        missing_worker_context = await client.post(
            f"/api/v1/analysis/internal/jobs/{claimed.id}/execute"
        )
        forged_worker_context = await client.post(
            f"/api/v1/analysis/internal/jobs/{claimed.id}/execute",
            headers={
                **worker_execution_headers(claimed, "review-test-worker"),
                JOB_EXECUTION_TOKEN_HEADER: "forged-worker-execution-token",
            },
        )
        executed = await client.post(
            f"/api/v1/analysis/internal/jobs/{claimed.id}/execute",
            headers=worker_execution_headers(claimed, "review-test-worker"),
        )
        repository.complete(claimed.id, "review-test-worker", executed.json())
        failed_run = await client.post(
            f"/api/v1/analysis/review-plans/{plan['key']}/actions",
            headers=manager,
            json={
                "action": "run_now",
                "expected_version": None,
                "idempotency_key": "review-run-now-worker-failure-001",
            },
        )
        failed_claim = repository.claim("review-failed-worker", lease_seconds=180)
        assert failed_claim is not None
        failed_at = datetime(2026, 8, 30, 3, 15, tzinfo=UTC)
        repository.fail(
            failed_claim.id,
            "review-failed-worker",
            error_code="job.handler_not_found",
            error_message="No handler registered for analysis.daily-store-review",
            retryable=False,
            now=failed_at,
        )
        refreshed = await client.get("/api/v1/analysis/review-plans", headers=manager)
        paused = await client.post(
            f"/api/v1/analysis/review-plans/{plan['key']}/actions",
            headers=manager,
            json={
                "action": "pause",
                "expected_version": plan["version"],
                "idempotency_key": "review-pause-001",
            },
        )
        stale_resume = await client.post(
            f"/api/v1/analysis/review-plans/{plan['key']}/actions",
            headers=manager,
            json={
                "action": "resume",
                "expected_version": plan["version"],
                "idempotency_key": "review-resume-stale-001",
            },
        )

    assert created.status_code == 200
    assert created.json()["idempotent"] is False
    assert repeated.json()["idempotent"] is True
    assert employee_read.status_code == 200
    assert employee_read.json()["can_manage"] is False
    assert len(employee_read.json()["plans"]) == 1
    assert employee_create.status_code == 403
    assert manager_enterprise.status_code == 403
    assert run_now.status_code == 200
    assert run_now.json()["schedule"]["runs"][0]["status"] == "queued"
    assert repeated_run.json()["idempotent"] is True
    assert missing_worker_context.status_code == 401
    assert (
        missing_worker_context.json()["error"]["code"]
        == "auth.worker_execution_context_required"
    )
    assert forged_worker_context.status_code == 403
    assert (
        forged_worker_context.json()["error"]["code"]
        == "authorization.worker_execution_context_denied"
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "succeeded"
    assert executed.json()["authorization"]["revalidated"] is True
    assert executed.json()["authorization"]["actor_principal_id"] == (
        "principal-ops-manager-zhou"
    )
    assert claimed.scope_type == "store"
    assert claimed.scope_id == "store-flagship"
    assert set(claimed.required_permissions) == {
        "analysis.run",
        "metric.query.execute",
        "action.propose",
    }
    assert failed_run.status_code == 200
    refreshed_run = next(
        item for item in refreshed.json()["runs"] if item["analysis_run_id"]
    )
    projected_failure = next(
        item for item in refreshed.json()["runs"] if item["background_job_id"] == failed_claim.id
    )
    assert refreshed_run["status"] == "succeeded"
    assert refreshed_run["analysis_run_id"] and refreshed_run["brief_id"]
    assert refreshed_run["proposal_count"] >= 1
    assert projected_failure["status"] == "failed"
    assert projected_failure["error_code"] == "job.handler_not_found"
    assert projected_failure["completed_at"] == "2026-08-30T03:15:00Z"
    assert refreshed.json()["stats"]["queued_or_running_count"] == 0
    assert refreshed.json()["stats"]["succeeded_count"] == 1
    assert refreshed.json()["stats"]["failed_count"] == 1
    assert refreshed.json()["stats"]["pending_proposal_count"] >= 1
    assert paused.json()["schedule"]["plans"][0]["status"] == "paused"
    assert stale_resume.status_code == 409
    assert stale_resume.json()["error"]["code"] == "analysis.schedule.version_conflict"
    with app.state.database.session() as session:
        assert session.scalar(select(func.count(StoreReviewPlan.id))) == 1
        assert session.scalar(select(func.count(StoreReviewScheduleRun.id))) == 2
        assert session.scalar(select(func.count(BackgroundJob.id))) == 2
        assert session.scalar(select(func.count(BusinessAnalysisRun.id))) == 1
        assert session.scalar(select(func.count(BusinessBrief.id))) == 1
        assert session.scalar(select(func.count(ActionProposal.id))) >= 1


@pytest.mark.anyio
async def test_worker_reauthorizes_scope_after_job_is_queued(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    seed_metric_series(app)
    manager = {"X-Zhixing-Demo-Actor": "manager"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/api/v1/analysis/review-plans",
            headers=manager,
            json={
                "name": "旗舰店撤权复核",
                "scope_key": "store-flagship",
                "window_days": 30,
                "timezone": "Asia/Shanghai",
                "local_time": "09:00",
                "weekdays": [1, 2, 3, 4, 5],
                "auto_propose_min_priority": "off",
                "client_request_key": "review-plan-scope-recheck-001",
            },
        )
        plan = created.json()["schedule"]["plans"][0]
        queued = await client.post(
            f"/api/v1/analysis/review-plans/{plan['key']}/actions",
            headers=manager,
            json={
                "action": "run_now",
                "expected_version": None,
                "idempotency_key": "review-run-scope-recheck-001",
            },
        )
        assert queued.status_code == 200
        repository = JobRepository(app.state.database.engine)
        claimed = repository.claim("review-scope-worker", lease_seconds=180)
        assert claimed is not None

        with app.state.database.session() as session:
            assignment_ids = list(
                session.scalars(
                    select(RoleAssignment.id).where(
                        RoleAssignment.principal_id == "principal-ops-manager-zhou"
                    )
                )
            )
            grant = session.scalar(
                select(ScopeGrant).where(
                    ScopeGrant.role_assignment_id.in_(assignment_ids),
                    ScopeGrant.scope_type == "store",
                )
            )
            assert grant is not None
            grant.scope_ids = ["store-outlet"]
            session.commit()

        denied = await client.post(
            f"/api/v1/analysis/internal/jobs/{claimed.id}/execute",
            headers=worker_execution_headers(claimed, "review-scope-worker"),
        )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "authorization.scope_denied"
    repository.fail(
        claimed.id,
        "review-scope-worker",
        error_code=denied.json()["error"]["code"],
        error_message=denied.json()["error"]["message"],
        retryable=False,
    )
    with app.state.database.session() as session:
        decision = session.scalar(
            select(AuthorizationDecision)
            .where(
                AuthorizationDecision.actor_principal_id
                == "principal-ops-manager-zhou",
                AuthorizationDecision.run_id == claimed.run_id,
                AuthorizationDecision.decision == "deny",
            )
            .order_by(AuthorizationDecision.decided_at.desc())
        )
        schedule_run = session.scalar(
            select(StoreReviewScheduleRun).where(
                StoreReviewScheduleRun.background_job_id == claimed.id
            )
        )
        job = session.get(BackgroundJob, claimed.id)
    assert decision is not None
    assert decision.reason == "resource_scope_not_granted"
    assert decision.policy_version != claimed.permission_set_version
    assert schedule_run is not None and schedule_run.status == "failed"
    assert job is not None and job.status == "failed"
    assert job.execution_token_hash is None


def test_dispatcher_enqueues_due_plan_once_and_advances_schedule(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))
    now = datetime(2026, 8, 31, 1, 0, tzinfo=UTC)
    with app.state.database.session() as session:
        session.add(
            StoreReviewPlan(
                id="store_review_plan_due",
                enterprise_id="ent_zhixing_demo",
                plan_key="review-store-flagship-due",
                name="到期巡店计划",
                scope_type="store",
                scope_key="store-flagship",
                scope_label="旗舰店",
                window_days=30,
                timezone="Asia/Shanghai",
                local_time="08:30",
                weekdays=[1, 2, 3, 4, 5],
                auto_propose_min_priority="off",
                status="active",
                next_run_at=now - timedelta(minutes=30),
                last_enqueued_at=None,
                created_by_principal_id="principal-ops-manager-zhou",
                actor_snapshot={},
                idempotency_key="review-plan-due-001",
                last_action=None,
                last_action_idempotency_key=None,
                version=1,
                created_at=now - timedelta(days=1),
                updated_at=now - timedelta(days=1),
            )
        )
        session.commit()
    assert dispatch_due_review_plans(app.state.database, now=now) == 1
    assert dispatch_due_review_plans(app.state.database, now=now) == 0
    with app.state.database.session() as session:
        plan = session.get(StoreReviewPlan, "store_review_plan_due")
        assert plan is not None and plan.next_run_at is not None
        assert plan.last_enqueued_at is not None
        assert plan.last_enqueued_at.replace(tzinfo=UTC) == now
        assert plan.next_run_at.replace(tzinfo=UTC) > now
        assert session.scalar(select(func.count(StoreReviewScheduleRun.id))) == 1
    next_run = calculate_next_run_at(
        timezone="Asia/Shanghai",
        local_time="09:00",
        weekdays=[1, 2, 3, 4, 5],
        after=datetime(2026, 8, 28, 2, 0, tzinfo=UTC),
    )
    assert next_run.isoformat() == "2026-08-31T01:00:00+00:00"
