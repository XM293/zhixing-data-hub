from __future__ import annotations

from pathlib import Path
from threading import Event
from time import monotonic

import httpx
import pytest
from sqlalchemy import create_engine
from zhixing_jobs import (
    JOB_EXECUTION_TOKEN_HEADER,
    WORKER_ID_HEADER,
    EnqueueJob,
    JobExecutionContext,
    JobRepository,
    JobsBase,
    PermanentJobError,
)
from zhixing_observability import REQUEST_ID_HEADER, RUN_ID_HEADER

from zhixing_worker.config import WorkerSettings
from zhixing_worker.main import (
    build_analysis_review_handler,
    build_runner,
    lingxing_sync_handler,
    run,
    wait_for_schema,
)


def test_worker_builds_with_registered_business_handler(tmp_path: Path) -> None:
    database_path = tmp_path / "worker_test.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    JobsBase.metadata.create_all(engine)
    settings = WorkerSettings(
        database_url=f"sqlite+pysqlite:///{database_path.as_posix()}",
        worker_id="worker-unit",
        poll_seconds=0.01,
        lease_seconds=1,
        retry_delay_seconds=0,
        schema_wait_seconds=0.1,
    )

    wait_for_schema(engine, settings.schema_wait_seconds)
    runner = build_runner(settings, engine)
    assert set(runner.handlers) == {
        "system.noop",
        "analysis.daily-store-review",
        "data-source.sync",
    }
    assert runner.run_once() is None
    engine.dispose()


def test_worker_once_starts_independently(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    database_path = tmp_path / "worker_once_test.db"
    database_url = f"sqlite+pysqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    JobsBase.metadata.create_all(engine)
    engine.dispose()
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("WORKER_SCHEMA_WAIT_SECONDS", "0.1")

    assert run(once=True, stop_event=Event()) == 0


def test_worker_reports_missing_migration(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'empty_test.db').as_posix()}")
    with pytest.raises(RuntimeError, match="pnpm db:upgrade"):
        wait_for_schema(engine, 0)
    engine.dispose()


def test_lingxing_handler_requires_explicit_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINGXING_ENABLED", "true")
    monkeypatch.setenv("LINGXING_APP_ID", "")
    monkeypatch.setenv("LINGXING_APP_SECRET", "")
    job = type("Job", (), {"payload": {"provider": "lingxing", "resource_key": "shops"}})()
    context = type("Context", (), {"ensure_active": lambda self: None})()
    with pytest.raises(PermanentJobError, match="凭据未配置"):
        lingxing_sync_handler(job, context)  # type: ignore[arg-type]


def test_lingxing_handler_blocks_non_official_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINGXING_ENABLED", "true")
    monkeypatch.setenv("LINGXING_APP_ID", "synthetic-app")
    monkeypatch.setenv("LINGXING_APP_SECRET", "synthetic-secret")
    monkeypatch.setenv("LINGXING_BASE_URL", "https://example.test")
    job = type("Job", (), {"payload": {"provider": "lingxing", "resource_key": "shops"}})()
    context = type("Context", (), {"ensure_active": lambda self: None})()
    with pytest.raises(PermanentJobError, match="官方只读 allowlist"):
        lingxing_sync_handler(job, context)  # type: ignore[arg-type]


def test_lingxing_disabled_provider_never_accesses_credentials(monkeypatch):
    monkeypatch.setenv("LINGXING_ENABLED", "false")
    job = type("Job", (), {"payload": {"provider": "lingxing", "resource_key": "shops"}})()
    context = type("Context", (), {"ensure_active": lambda self: None})()
    with pytest.raises(PermanentJobError) as error:
        lingxing_sync_handler(job, context)
    assert error.value.code == "sync.provider_disabled"


def test_analysis_review_handler_maps_success_and_permanent_rejection(tmp_path: Path) -> None:
    database_path = tmp_path / "worker_handler_test.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    JobsBase.metadata.create_all(engine)
    repository = JobRepository(engine)
    repository.enqueue(
        EnqueueJob(
            enterprise_id="ent_test",
            job_type="analysis.daily-store-review",
            payload={"schedule_run_id": "run_1"},
            idempotency_key="review-handler-001",
            initiator_type="principal",
            initiator_id="principal_test",
            actor_snapshot={"principal_id": "principal_test"},
            permission_set_version="access-worker-test",
            required_permissions=("analysis.run", "metric.query.execute"),
            scope_type="store",
            scope_id="store-test",
            run_id="run_review_handler",
        )
    )
    job = repository.claim("worker-handler")
    assert job is not None
    context = JobExecutionContext(
        job_id=job.id,
        enterprise_id=job.enterprise_id,
        initiator_type=job.initiator_type,
        initiator_id=job.initiator_id,
        actor_snapshot=job.actor_snapshot,
        permission_set_version=job.permission_set_version,
        required_permissions=job.required_permissions,
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        deadline_monotonic=monotonic() + 5,
    )
    settings = WorkerSettings(
        database_url=f"sqlite+pysqlite:///{database_path.as_posix()}",
        worker_id="worker-handler",
        poll_seconds=0.01,
        lease_seconds=1,
        retry_delay_seconds=0,
        schema_wait_seconds=0.1,
        api_base_url="http://test",
        api_timeout_seconds=2,
    )
    captured: list[httpx.Request] = []

    def success_response(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"status": "succeeded", "analysis_run_id": "analysis_1"},
            request=request,
        )

    success_handler = build_analysis_review_handler(
        settings,
        transport=httpx.MockTransport(success_response),
    )
    assert success_handler(job, context) == {
        "status": "succeeded",
        "analysis_run_id": "analysis_1",
    }
    assert captured[0].headers[WORKER_ID_HEADER] == "worker-handler"
    assert captured[0].headers[JOB_EXECUTION_TOKEN_HEADER] == job.execution_token
    assert captured[0].headers[REQUEST_ID_HEADER] == job.request_id
    assert captured[0].headers[RUN_ID_HEADER] == job.run_id
    rejected_handler = build_analysis_review_handler(
        settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                409,
                json={"error": {"code": "analysis.schedule.rejected", "message": "拒绝"}},
                request=request,
            )
        ),
    )
    with pytest.raises(PermanentJobError) as exc_info:
        rejected_handler(job, context)
    assert exc_info.value.code == "analysis.schedule.rejected"
    engine.dispose()
