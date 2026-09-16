from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from threading import Event
from time import monotonic

from sqlalchemy import Connection
from sqlalchemy.exc import InterfaceError, OperationalError
from zhixing_observability import TraceContext, bind_trace_context, log_event

from zhixing_jobs.contracts import JobRecord, JobStatus
from zhixing_jobs.repository import JobRepository, JobStateConflict

logger = logging.getLogger("zhixing.worker")


class JobContinuation(RuntimeError):
    """A durable progress boundary; distinct from failure and success."""
    def __init__(self, progress: int) -> None:
        super().__init__("job.continued")
        self.progress = progress


class RetryableJobError(RuntimeError):
    def __init__(self, message: str, code: str = "job.retryable_error", *,
                 retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        if retry_after_seconds is not None and not 0 <= retry_after_seconds <= 300:
            raise ValueError("retry delay must be within 0..300 seconds")
        self.code = code
        self.retry_after_seconds = retry_after_seconds


class PermanentJobError(RuntimeError):
    def __init__(self, message: str, code: str = "job.permanent_error") -> None:
        super().__init__(message)
        self.code = code


class JobTimeoutError(RetryableJobError):
    def __init__(self, message: str = "Job execution deadline exceeded") -> None:
        super().__init__(message, code="job.timeout")


@dataclass(frozen=True, slots=True)
class JobExecutionContext:
    job_id: str
    enterprise_id: str
    initiator_type: str
    initiator_id: str
    actor_snapshot: dict[str, object]
    permission_set_version: str
    required_permissions: tuple[str, ...]
    scope_type: str
    scope_id: str
    deadline_monotonic: float
    validate_lease: Callable[[], None] | None = field(default=None, repr=False, compare=False)
    fence: Callable[[Connection], None] | None = field(default=None, repr=False, compare=False)

    def ensure_active(self) -> None:
        if monotonic() > self.deadline_monotonic:
            raise JobTimeoutError()
        if self.validate_lease is not None:
            self.validate_lease()


JobHandler = Callable[
    [JobRecord, JobExecutionContext], Mapping[str, object] | None
]


@dataclass(frozen=True, slots=True)
class WorkerOutcome:
    job_id: str
    status: JobStatus
    attempt: int


class WorkerRunner:
    def __init__(
        self,
        repository: JobRepository,
        handlers: Mapping[str, JobHandler],
        *,
        worker_id: str,
        lease_seconds: float = 30.0,
        retry_delay_seconds: float = 1.0,
        poll_seconds: float = 0.5,
        before_poll: Callable[[], None] | None = None,
    ) -> None:
        self.repository = repository
        self.handlers = dict(handlers)
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self.poll_seconds = poll_seconds
        self.before_poll = before_poll

    def run_once(self) -> WorkerOutcome | None:
        if self.before_poll is not None:
            self.before_poll()
        recovered = self.repository.recover_expired()
        if recovered:
            log_event(logger, "worker.jobs.recovered", worker_id=self.worker_id, count=recovered)
        job = self.repository.claim(self.worker_id, lease_seconds=self.lease_seconds)
        if job is None:
            return None

        trace = TraceContext(request_id=job.request_id, run_id=job.run_id)
        started = monotonic()
        execution = JobExecutionContext(
            job_id=job.id,
            enterprise_id=job.enterprise_id,
            initiator_type=job.initiator_type,
            initiator_id=job.initiator_id,
            actor_snapshot=job.actor_snapshot,
            permission_set_version=job.permission_set_version,
            required_permissions=job.required_permissions,
            scope_type=job.scope_type,
            scope_id=job.scope_id,
            deadline_monotonic=started + job.timeout_seconds,
            validate_lease=lambda: self.repository.ensure_execution_active(
                job.id, self.worker_id, job.execution_token
            ),
            fence=lambda connection: self.repository.fence_execution(
                connection, job.id, self.worker_id, job.execution_token),
        )
        with bind_trace_context(trace):
            log_event(
                logger,
                "worker.job.started",
                job_id=job.id,
                job_type=job.job_type,
                enterprise_id=job.enterprise_id,
                attempt=job.attempt,
                initiator_type=job.initiator_type,
                initiator_id=job.initiator_id,
                permission_set_version=job.permission_set_version,
                scope_type=job.scope_type,
                scope_id=job.scope_id,
            )
            handler = self.handlers.get(job.job_type)
            if handler is None:
                return self._fail(
                    job,
                    PermanentJobError(
                        f"No handler registered for {job.job_type}",
                        code="job.handler_not_found",
                    ),
                    retryable=False,
                )
            try:
                result = handler(job, execution)
                execution.ensure_active()
            except JobContinuation as continuation:
                try:
                    continued = self.repository.continue_job(
                        job.id, self.worker_id, progress=continuation.progress,
                        execution_token=job.execution_token)
                except JobStateConflict:
                    return self._current_outcome(job)
                except ValueError:
                    return self._fail(job, PermanentJobError("任务续跑没有新增进度",
                        code="job.continuation_without_progress"), retryable=False)
                log_event(logger, "worker.job.continued", job_id=job.id,
                          attempt=job.attempt, progress=continuation.progress)
                return WorkerOutcome(job_id=job.id, status=continued.status, attempt=job.attempt)
            except JobStateConflict:
                current = self.repository.get(job.id)
                return WorkerOutcome(job_id=job.id,
                                     status=current.status if current else "cancelled",
                                     attempt=job.attempt)
            except JobTimeoutError as error:
                return self._fail(job, error, retryable=True, timed_out=True)
            except RetryableJobError as error:
                return self._fail(job, error, retryable=True)
            except PermanentJobError as error:
                return self._fail(job, error, retryable=False)
            except Exception:
                return self._fail(
                    job,
                    RetryableJobError("后台任务执行异常", code="job.unhandled_error"),
                    retryable=True,
                )

            try:
                completed = self.repository.complete(
                    job.id, self.worker_id, dict(result) if result is not None else None,
                    execution_token=job.execution_token,
                )
            except JobStateConflict:
                return self._current_outcome(job)
            log_event(
                logger,
                "worker.job.succeeded",
                job_id=job.id,
                job_type=job.job_type,
                enterprise_id=job.enterprise_id,
                attempt=job.attempt,
                duration_ms=round((monotonic() - started) * 1000, 2),
            )
            return WorkerOutcome(job_id=completed.id, status=completed.status, attempt=job.attempt)

    def run_forever(self, stop_event: Event) -> None:
        log_event(logger, "worker.started", worker_id=self.worker_id)
        connection_failures = 0
        try:
            while not stop_event.is_set():
                try:
                    outcome = self.run_once()
                except (OperationalError, InterfaceError) as error:
                    connection_failures = min(connection_failures + 1, 6)
                    delay = min(30, 2 ** (connection_failures - 1))
                    log_event(logger, "worker.database.retry", level=logging.WARNING,
                              worker_id=self.worker_id, error_type=type(error).__name__,
                              retry_seconds=delay)
                    stop_event.wait(delay)
                    continue
                connection_failures = 0
                if outcome is None:
                    stop_event.wait(self.poll_seconds)
        finally:
            log_event(logger, "worker.stopped", worker_id=self.worker_id)

    def _fail(
        self,
        job: JobRecord,
        error: RetryableJobError | PermanentJobError,
        *,
        retryable: bool,
        timed_out: bool = False,
    ) -> WorkerOutcome:
        failures = job.attempt - job.continuation_count
        retry_delay = min(300, self.retry_delay_seconds * (2 ** min(max(failures - 1, 0), 10)))
        if isinstance(error, RetryableJobError) and error.retry_after_seconds is not None:
            retry_delay = error.retry_after_seconds
        try:
            failed = self.repository.fail(
                job.id, self.worker_id, error_code=error.code, error_message=str(error),
                retryable=retryable, retry_delay_seconds=retry_delay, timed_out=timed_out,
                execution_token=job.execution_token,
            )
        except JobStateConflict:
            return self._current_outcome(job)
        log_event(
            logger,
            "worker.job.retry_scheduled" if failed.status == "retry_wait" else "worker.job.failed",
            level=logging.WARNING if failed.status == "retry_wait" else logging.ERROR,
            job_id=job.id,
            job_type=job.job_type,
            enterprise_id=job.enterprise_id,
            attempt=job.attempt,
            error_code=error.code,
            retryable=retryable,
        )
        return WorkerOutcome(job_id=failed.id, status=failed.status, attempt=job.attempt)

    def _current_outcome(self, job: JobRecord) -> WorkerOutcome:
        current = self.repository.get(job.id)
        return WorkerOutcome(job_id=job.id, status=current.status if current else "cancelled",
                             attempt=job.attempt)
