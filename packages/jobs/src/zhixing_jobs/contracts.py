from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

JobStatus = Literal["queued", "running", "retry_wait", "succeeded", "failed", "cancelled"]

WORKER_ID_HEADER = "X-Zhixing-Worker-ID"
JOB_EXECUTION_TOKEN_HEADER = "X-Zhixing-Job-Execution-Token"


@dataclass(frozen=True, slots=True)
class EnqueueJob:
    enterprise_id: str
    job_type: str
    payload: dict[str, object]
    idempotency_key: str
    initiator_type: str
    initiator_id: str
    actor_snapshot: dict[str, object]
    permission_set_version: str
    required_permissions: tuple[str, ...]
    scope_type: str
    scope_id: str
    run_id: str
    request_id: str | None = None
    priority: int = 0
    max_attempts: int = 3
    timeout_seconds: float = 300.0


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: str
    enterprise_id: str
    job_type: str
    payload: dict[str, object]
    status: JobStatus
    priority: int
    attempt: int
    max_attempts: int
    timeout_seconds: float
    available_at: datetime
    idempotency_key: str
    initiator_type: str
    initiator_id: str
    actor_snapshot: dict[str, object]
    permission_set_version: str
    required_permissions: tuple[str, ...]
    scope_type: str
    scope_id: str
    request_id: str
    run_id: str
    worker_id: str | None
    result: dict[str, object] | None
    last_error_code: str | None
    last_error_message: str | None
    created_at: datetime
    updated_at: datetime
    execution_token: str | None = field(default=None, repr=False, compare=False)
    continuation_count: int = 0
    continuation_progress: int = 0


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    job: JobRecord
    created: bool
