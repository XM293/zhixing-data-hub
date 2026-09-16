from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Thread
from time import sleep

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from zhixing_jobs import (
    BackgroundJob,
    EnqueueJob,
    JobAttempt,
    JobContinuation,
    JobExecutionContext,
    JobRecord,
    JobRepository,
    JobsBase,
    RetryableJobError,
    WorkerRunner,
)


def create_repository(tmp_path: Path) -> tuple[JobRepository, object]:
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'jobs_test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    JobsBase.metadata.create_all(engine)
    return JobRepository(engine), engine


def request(
    *,
    key: str = "probe-001",
    max_attempts: int = 3,
    timeout_seconds: float = 1.0,
) -> EnqueueJob:
    return EnqueueJob(
        enterprise_id="ent_test",
        job_type="test.probe",
        payload={"value": 42},
        idempotency_key=key,
        initiator_type="user",
        initiator_id="user_ceo",
        actor_snapshot={"principal_id": "user_ceo", "display_name": "CEO"},
        permission_set_version="access-test-v1",
        required_permissions=("test.probe.execute",),
        scope_type="enterprise",
        scope_id="ent_test",
        request_id="req_jobs_1234",
        run_id="run_jobs_1234",
        max_attempts=max_attempts,
        timeout_seconds=timeout_seconds,
    )


def test_enqueue_is_idempotent_and_preserves_actor_trace(tmp_path: Path) -> None:
    repository, engine = create_repository(tmp_path)
    first = repository.enqueue(request())
    second = repository.enqueue(request())

    assert first.created is True
    assert second.created is False
    assert second.job.id == first.job.id
    assert repository.count() == 1
    assert first.job.enterprise_id == "ent_test"
    assert first.job.initiator_type == "user"
    assert first.job.initiator_id == "user_ceo"
    assert first.job.permission_set_version == "access-test-v1"
    assert first.job.required_permissions == ("test.probe.execute",)
    assert first.job.scope_type == "enterprise"
    assert first.job.scope_id == "ent_test"
    assert first.job.request_id == "req_jobs_1234"
    assert first.job.run_id == "run_jobs_1234"


def test_continuations_preserve_failure_budget_and_audit(tmp_path: Path) -> None:
    repository, engine = create_repository(tmp_path)
    queued = repository.enqueue(request(max_attempts=2))
    def handler(job, context):
        if job.continuation_count < 4:
            raise JobContinuation(job.continuation_progress + 100)
        raise RetryableJobError("Synthetic failure")
    worker = WorkerRunner(repository, {"test.probe": handler}, worker_id="verify",
                          retry_delay_seconds=0)
    for _ in range(4):
        assert worker.run_once().status == "queued"
    current = repository.get(queued.job.id)
    assert current.continuation_count == 4 and current.max_attempts == 2
    assert worker.run_once().status == "retry_wait"
    assert worker.run_once().status == "failed"
    with Session(engine) as session:
        attempts = session.scalars(select(JobAttempt).order_by(JobAttempt.attempt_no)).all()
        assert [item.status for item in attempts] == ["continued"] * 4 + [
            "retry_scheduled", "failed"]


def test_continuation_yields_to_already_waiting_jobs(tmp_path: Path, monkeypatch) -> None:
    repository, engine = create_repository(tmp_path)
    now = datetime(2026, 9, 10, tzinfo=UTC)
    first = repository.enqueue(request(key="backfill"), now=now).job
    claimed = repository.claim("worker", now=now + timedelta(seconds=1), lease_seconds=60)
    second = repository.enqueue(request(key="incremental"),
                                now=now + timedelta(seconds=2)).job
    monkeypatch.setattr("zhixing_jobs.repository.utc_now", lambda: now + timedelta(seconds=3))
    repository.continue_job(first.id, "worker", progress=1,
                            execution_token=claimed.execution_token)
    following = repository.claim("worker", now=now + timedelta(seconds=4))
    assert following.id == second.id
    repository.complete(second.id, "worker", {}, now=now + timedelta(seconds=4),
                        execution_token=following.execution_token)
    resumed = repository.claim("worker", now=now + timedelta(seconds=5))
    assert resumed.id == first.id and resumed.continuation_count == 1
    assert resumed.execution_token != claimed.execution_token


def test_continuation_requires_advancing_progress_and_current_lease(tmp_path: Path) -> None:
    import pytest

    from zhixing_jobs import JobStateConflict
    repository, engine = create_repository(tmp_path)
    queued = repository.enqueue(request())
    first = repository.claim("verify", lease_seconds=60)
    repository.continue_job(first.id, "verify", progress=100, execution_token=first.execution_token)
    with pytest.raises(JobStateConflict):
        repository.continue_job(first.id, "verify", progress=200,
                                execution_token=first.execution_token)
    second = repository.claim("verify", lease_seconds=60)
    with pytest.raises(ValueError):
        repository.continue_job(second.id, "verify", progress=100,
                                execution_token=second.execution_token)
    assert repository.get(queued.job.id).continuation_count == 1
    expired_at = datetime.now(UTC) - timedelta(seconds=1)
    with Session(engine) as session:
        session.get(BackgroundJob, second.id).lease_expires_at = expired_at
        session.commit()
    with pytest.raises(JobStateConflict):
        repository.continue_job(second.id, "verify", progress=200,
                                execution_token=second.execution_token)
    engine.dispose()


def test_cancellation_stops_running_handler_before_next_page(tmp_path: Path) -> None:
    repository, engine = create_repository(tmp_path)
    queued = repository.enqueue(request()).job
    persisted_pages: list[int] = []

    def handler(job: JobRecord, context: JobExecutionContext) -> dict[str, object]:
        context.ensure_active()
        persisted_pages.append(1)
        with Session(repository.engine) as session:
            repository.cancel_in_session(session, job.id, job.enterprise_id)
            session.commit()
        context.ensure_active()
        persisted_pages.append(2)
        return {}

    outcome = WorkerRunner(repository, {"test.probe": handler}, worker_id="worker-test").run_once()
    assert outcome is not None and outcome.status == "cancelled"
    assert persisted_pages == [1]
    assert repository.get(queued.id).status == "cancelled"
    engine.dispose()


def test_runner_retries_then_completes(tmp_path: Path) -> None:
    repository, engine = create_repository(tmp_path)
    queued = repository.enqueue(request(max_attempts=2)).job
    calls = 0

    def handler(
        _job: JobRecord,
        _context: JobExecutionContext,
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RetryableJobError("temporary dependency failure", code="test.temporary")
        return {"handled": True}

    runner = WorkerRunner(
        repository,
        {"test.probe": handler},
        worker_id="worker-test",
        retry_delay_seconds=0,
    )
    first = runner.run_once()
    second = runner.run_once()

    assert first is not None and first.status == "retry_wait"
    assert second is not None and second.status == "succeeded"
    finished = repository.get(queued.id)
    assert finished is not None
    assert finished.attempt == 2
    assert finished.result == {"handled": True}
    with Session(engine) as session:
        attempts = list(
            session.scalars(
                select(JobAttempt)
                .where(JobAttempt.job_id == queued.id)
                .order_by(JobAttempt.attempt_no)
            )
        )
    assert [item.status for item in attempts] == ["retry_scheduled", "succeeded"]
    engine.dispose()


def test_runner_marks_execution_timeout(tmp_path: Path) -> None:
    repository, engine = create_repository(tmp_path)
    queued = repository.enqueue(request(max_attempts=1, timeout_seconds=0.005)).job

    def slow_handler(
        _job: JobRecord,
        _context: JobExecutionContext,
    ) -> dict[str, object]:
        sleep(0.02)
        return {"late": True}

    runner = WorkerRunner(
        repository,
        {"test.probe": slow_handler},
        worker_id="worker-timeout",
        retry_delay_seconds=0,
    )
    outcome = runner.run_once()
    failed = repository.get(queued.id)

    assert outcome is not None and outcome.status == "failed"
    assert failed is not None
    assert failed.last_error_code == "job.timeout"
    with Session(engine) as session:
        attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == queued.id))
    assert attempt is not None and attempt.status == "timed_out"
    engine.dispose()


def test_expired_lease_returns_job_to_retry_queue(tmp_path: Path) -> None:
    repository, engine = create_repository(tmp_path)
    current = datetime(2026, 8, 28, tzinfo=UTC)
    queued = repository.enqueue(
        request(max_attempts=2, timeout_seconds=0.001),
        now=current,
    ).job
    claimed = repository.claim("worker-lost", lease_seconds=0.01, now=current)
    assert claimed is not None
    assert claimed.execution_token
    persisted_claim = repository.get(queued.id)
    assert persisted_claim is not None and persisted_claim.execution_token is None
    with Session(engine) as session:
        stored_claim = session.get(BackgroundJob, queued.id)
        assert stored_claim is not None
        assert stored_claim.execution_token_hash
        assert len(stored_claim.execution_token_hash) == 64
        assert stored_claim.execution_token_hash != claimed.execution_token

    recovered = repository.recover_expired(now=current + timedelta(seconds=2))
    job = repository.get(queued.id)

    assert recovered == 1
    assert job is not None and job.status == "retry_wait"
    assert job.last_error_code == "job.lease_expired"
    with Session(engine) as session:
        stored_recovered = session.get(BackgroundJob, queued.id)
        assert stored_recovered is not None
        assert stored_recovered.execution_token_hash is None
    engine.dispose()


def test_idle_worker_stops_without_waiting_for_poll_timeout(tmp_path: Path) -> None:
    repository, engine = create_repository(tmp_path)
    runner = WorkerRunner(
        repository,
        {},
        worker_id="worker-stop",
        poll_seconds=2,
    )
    stop_event = Event()
    thread = Thread(target=runner.run_forever, args=(stop_event,))
    thread.start()
    sleep(0.02)
    stop_event.set()
    thread.join(timeout=0.5)

    assert thread.is_alive() is False
    engine.dispose()
