from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
from typing import cast
from uuid import uuid4

from sqlalchemy import Connection, Engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from zhixing_observability import resolve_trace_id

from zhixing_jobs.contracts import EnqueueJob, EnqueueResult, JobRecord, JobStatus
from zhixing_jobs.models import BackgroundJob, JobAttempt

CLAIMABLE_STATUSES = ("queued", "retry_wait")


class JobStateConflict(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


def _record(job: BackgroundJob, *, execution_token: str | None = None) -> JobRecord:
    return JobRecord(
        id=job.id,
        enterprise_id=job.enterprise_id,
        job_type=job.job_type,
        payload=dict(job.payload),
        status=cast(JobStatus, job.status),
        priority=job.priority,
        attempt=job.attempt,
        max_attempts=job.max_attempts,
        continuation_count=job.continuation_count,
        continuation_progress=job.continuation_progress,
        timeout_seconds=job.timeout_seconds,
        available_at=job.available_at,
        idempotency_key=job.idempotency_key,
        initiator_type=job.initiator_type,
        initiator_id=job.initiator_id,
        actor_snapshot=dict(job.actor_snapshot),
        permission_set_version=job.permission_set_version,
        required_permissions=tuple(job.required_permissions),
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        request_id=job.request_id,
        run_id=job.run_id,
        worker_id=job.worker_id,
        result=dict(job.result) if job.result is not None else None,
        last_error_code=job.last_error_code,
        last_error_message=job.last_error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        execution_token=execution_token,
    )


class JobRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._sessions = sessionmaker(bind=engine, expire_on_commit=False)

    def enqueue(self, request: EnqueueJob, *, now: datetime | None = None) -> EnqueueResult:
        self._validate_enqueue(request)
        current = now or utc_now()
        lookup = (
            BackgroundJob.enterprise_id == request.enterprise_id,
            BackgroundJob.job_type == request.job_type,
            BackgroundJob.idempotency_key == request.idempotency_key,
        )
        try:
            with self._sessions.begin() as session:
                return self.enqueue_in_session(session, request, now=current)
        except IntegrityError:
            with self._sessions() as session:
                existing = session.scalar(select(BackgroundJob).where(*lookup))
                if existing is None:
                    raise
                return EnqueueResult(job=_record(existing), created=False)

    def enqueue_in_session(
        self, session: Session, request: EnqueueJob, *, now: datetime | None = None
    ) -> EnqueueResult:
        """Join a caller-owned transaction, so domain intent and job commit together."""
        self._validate_enqueue(request)
        current = now or utc_now()
        existing = session.scalar(select(BackgroundJob).where(
            BackgroundJob.enterprise_id == request.enterprise_id,
            BackgroundJob.job_type == request.job_type,
            BackgroundJob.idempotency_key == request.idempotency_key,
        ))
        if existing is not None:
            return EnqueueResult(job=_record(existing), created=False)
        job = BackgroundJob(
            id=f"job_{uuid4().hex}", enterprise_id=request.enterprise_id,
            job_type=request.job_type, payload=request.payload, status="queued",
            priority=request.priority, attempt=0, max_attempts=request.max_attempts,
            timeout_seconds=request.timeout_seconds, available_at=current,
            idempotency_key=request.idempotency_key, initiator_type=request.initiator_type,
            initiator_id=request.initiator_id, actor_snapshot=request.actor_snapshot,
            permission_set_version=request.permission_set_version,
            required_permissions=list(request.required_permissions), scope_type=request.scope_type,
            scope_id=request.scope_id, execution_token_hash=None,
            request_id=resolve_trace_id(request.request_id, "req"),
            run_id=resolve_trace_id(request.run_id, "run"), created_at=current, updated_at=current,
        )
        session.add(job)
        session.flush()
        return EnqueueResult(job=_record(job), created=True)

    def claim(
        self,
        worker_id: str,
        *,
        lease_seconds: float = 30.0,
        now: datetime | None = None,
    ) -> JobRecord | None:
        current = now or utc_now()
        with self._sessions.begin() as session:
            job = session.scalar(
                select(BackgroundJob)
                .where(
                    BackgroundJob.status.in_(CLAIMABLE_STATUSES),
                    BackgroundJob.available_at <= current,
                )
                .order_by(BackgroundJob.priority.desc(), BackgroundJob.available_at,
                          BackgroundJob.created_at, BackgroundJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                return None
            job.status = "running"
            job.attempt += 1
            job.worker_id = worker_id
            execution_token = token_urlsafe(32)
            job.execution_token_hash = sha256(execution_token.encode("utf-8")).hexdigest()
            job.claimed_at = current
            job.heartbeat_at = current
            job.lease_expires_at = current + timedelta(
                seconds=max(lease_seconds, job.timeout_seconds + 1.0)
            )
            job.started_at = job.started_at or current
            job.updated_at = current
            session.add(
                JobAttempt(
                    id=f"attempt_{uuid4().hex}",
                    job_id=job.id,
                    attempt_no=job.attempt,
                    worker_id=worker_id,
                    status="running",
                    started_at=current,
                )
            )
            session.flush()
            return _record(job, execution_token=execution_token)

    def complete(
        self,
        job_id: str,
        worker_id: str,
        result: dict[str, object] | None,
        *,
        now: datetime | None = None,
        execution_token: str | None = None,
    ) -> JobRecord:
        current = now or utc_now()
        with self._sessions.begin() as session:
            job = self._owned_running_job(session, job_id, worker_id, execution_token)
            attempt = self._current_attempt(session, job)
            job.status = "succeeded"
            job.result = result
            job.finished_at = current
            job.lease_expires_at = None
            job.execution_token_hash = None
            job.heartbeat_at = current
            job.updated_at = current
            attempt.status = "succeeded"
            attempt.finished_at = current
            session.flush()
            return _record(job)

    def continue_job(self, job_id: str, worker_id: str, *, progress: int,
                     execution_token: str | None = None) -> JobRecord:
        current = utc_now()
        with self._sessions.begin() as session:
            if not execution_token:
                raise JobStateConflict("续跑缺少有效领取令牌")
            self.fence_execution(session.connection(), job_id, worker_id, execution_token)
            job = self._owned_running_job(session, job_id, worker_id, execution_token)
            if (isinstance(progress, bool) or not isinstance(progress, int)
                    or progress <= job.continuation_progress):
                raise ValueError("job.continuation_requires_progress")
            attempt = self._current_attempt(session, job)
            job.continuation_count += 1
            job.continuation_progress = progress
            job.status = "queued"
            job.available_at = current
            job.finished_at = None
            job.worker_id = None
            job.lease_expires_at = None
            job.execution_token_hash = None
            job.last_error_code = None
            job.last_error_message = None
            job.updated_at = current
            attempt.status = "continued"
            attempt.finished_at = current
            session.flush()
            return _record(job)

    def fail(
        self,
        job_id: str,
        worker_id: str,
        *,
        error_code: str,
        error_message: str,
        retryable: bool,
        retry_delay_seconds: float = 0.0,
        timed_out: bool = False,
        now: datetime | None = None,
        execution_token: str | None = None,
    ) -> JobRecord:
        current = now or utc_now()
        with self._sessions.begin() as session:
            job = self._owned_running_job(session, job_id, worker_id, execution_token)
            attempt = self._current_attempt(session, job)
            should_retry = retryable and job.attempt - job.continuation_count < job.max_attempts
            job.status = "retry_wait" if should_retry else "failed"
            job.available_at = current + timedelta(seconds=retry_delay_seconds)
            job.finished_at = None if should_retry else current
            job.worker_id = None
            job.lease_expires_at = None
            job.execution_token_hash = None
            job.last_error_code = error_code
            job.last_error_message = error_message[:1000]
            job.updated_at = current
            attempt.status = "timed_out" if timed_out else (
                "retry_scheduled" if should_retry else "failed"
            )
            attempt.finished_at = current
            attempt.error_code = error_code
            attempt.error_message = error_message[:1000]
            session.flush()
            return _record(job)

    def recover_expired(self, *, now: datetime | None = None) -> int:
        current = now or utc_now()
        with self._sessions.begin() as session:
            expired = list(
                session.scalars(
                    select(BackgroundJob)
                    .where(
                        BackgroundJob.status == "running",
                        BackgroundJob.lease_expires_at.is_not(None),
                        BackgroundJob.lease_expires_at <= current,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            for job in expired:
                attempt = self._current_attempt(session, job)
                should_retry = job.attempt - job.continuation_count < job.max_attempts
                job.status = "retry_wait" if should_retry else "failed"
                job.available_at = current
                job.finished_at = None if should_retry else current
                job.worker_id = None
                job.lease_expires_at = None
                job.execution_token_hash = None
                job.last_error_code = "job.lease_expired"
                job.last_error_message = "Worker lease expired before completion"
                job.updated_at = current
                attempt.status = "timed_out"
                attempt.finished_at = current
                attempt.error_code = "job.lease_expired"
                attempt.error_message = job.last_error_message
            return len(expired)

    def get(self, job_id: str) -> JobRecord | None:
        with self._sessions() as session:
            job = session.get(BackgroundJob, job_id)
            return _record(job) if job is not None else None

    def count(self) -> int:
        with self._sessions() as session:
            return int(session.scalar(select(func.count(BackgroundJob.id))) or 0)

    def ensure_execution_active(self, job_id: str, worker_id: str, token: str | None) -> None:
        with self._sessions() as session:
            job = session.get(BackgroundJob, job_id)
            expiry = job.lease_expires_at if job else None
            if expiry is not None and expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=UTC)
            if (job is None or job.status != "running" or job.worker_id != worker_id
                    or expiry is None or expiry <= utc_now() or not token
                    or not compare_digest(job.execution_token_hash or "",
                                          sha256(token.encode()).hexdigest())):
                raise JobStateConflict("任务租约已失效或任务已取消")

    @staticmethod
    def fence_execution(connection: Connection, job_id: str,
                        worker_id: str, token: str | None) -> None:
        if not token:
            raise JobStateConflict("任务缺少当前执行租约")
        current = connection.execute(select(BackgroundJob.id).where(
            BackgroundJob.id == job_id, BackgroundJob.worker_id == worker_id,
            BackgroundJob.status == "running", BackgroundJob.lease_expires_at > utc_now(),
            BackgroundJob.execution_token_hash == sha256(token.encode()).hexdigest(),
        ).with_for_update()).scalar_one_or_none()
        if current is None:
            raise JobStateConflict("任务租约已失效或任务已取消")

    def cancel_in_session(self, session: Session, job_id: str, enterprise_id: str) -> JobRecord:
        job = session.scalar(select(BackgroundJob).where(
            BackgroundJob.id == job_id, BackgroundJob.enterprise_id == enterprise_id
        ).with_for_update())
        if job is None:
            raise LookupError("任务不存在")
        if job.status not in {"succeeded", "failed", "cancelled"}:
            now = utc_now()
            if job.status == "running":
                attempt = self._current_attempt(session, job)
                attempt.status, attempt.finished_at = "cancelled", now
            job.status, job.finished_at, job.updated_at = "cancelled", now, now
            job.worker_id, job.lease_expires_at, job.execution_token_hash = None, None, None
            session.flush()
        return _record(job)

    @staticmethod
    def _validate_enqueue(request: EnqueueJob) -> None:
        required = {
            "enterprise_id": request.enterprise_id,
            "job_type": request.job_type,
            "idempotency_key": request.idempotency_key,
            "initiator_type": request.initiator_type,
            "initiator_id": request.initiator_id,
            "permission_set_version": request.permission_set_version,
            "scope_type": request.scope_type,
            "scope_id": request.scope_id,
            "run_id": request.run_id,
        }
        missing = [key for key, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"任务缺少必填字段：{', '.join(missing)}")
        if not request.actor_snapshot:
            raise ValueError("任务缺少发起人快照")
        if request.initiator_type == "principal" and request.actor_snapshot.get(
            "principal_id"
        ) != request.initiator_id:
            raise ValueError("任务发起人快照与 initiator_id 不一致")
        if len(set(request.required_permissions)) != len(request.required_permissions):
            raise ValueError("任务声明权限不能重复")
        if any(not item.strip() for item in request.required_permissions):
            raise ValueError("任务声明权限不能为空")
        if request.max_attempts < 1:
            raise ValueError("max_attempts 必须大于等于 1")
        if request.timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0")

    @staticmethod
    def _owned_running_job(session: Session, job_id: str, worker_id: str,
                           execution_token: str | None = None) -> BackgroundJob:
        job = session.scalar(
            select(BackgroundJob).where(BackgroundJob.id == job_id).with_for_update()
        )
        if job is None or job.status != "running" or job.worker_id != worker_id:
            raise JobStateConflict(f"任务 {job_id} 不属于运行中的 Worker {worker_id}")
        if execution_token is not None and not compare_digest(
            job.execution_token_hash or "", sha256(execution_token.encode()).hexdigest()
        ):
            raise JobStateConflict("任务执行租约已被替换")
        return job

    @staticmethod
    def _current_attempt(session: Session, job: BackgroundJob) -> JobAttempt:
        attempt = session.scalar(
            select(JobAttempt).where(
                JobAttempt.job_id == job.id,
                JobAttempt.attempt_no == job.attempt,
            )
        )
        if attempt is None:
            raise JobStateConflict(f"任务 {job.id} 缺少第 {job.attempt} 次执行记录")
        return attempt
