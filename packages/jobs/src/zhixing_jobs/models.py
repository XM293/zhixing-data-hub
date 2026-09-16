from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class JobsBase(DeclarativeBase):
    pass


class BackgroundJob(JobsBase):
    __tablename__ = "background_jobs"
    __table_args__ = (
        UniqueConstraint(
            "enterprise_id",
            "job_type",
            "idempotency_key",
            name="uq_background_jobs_idempotency",
        ),
        Index("ix_background_jobs_enterprise_id", "enterprise_id"),
        Index("ix_background_jobs_run_id", "run_id"),
        Index("ix_background_jobs_claim", "status", "available_at", "priority", "created_at"),
        Index("ix_background_jobs_lease", "status", "lease_expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(64))
    job_type: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, object]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32))
    priority: Mapped[int] = mapped_column(Integer)
    attempt: Mapped[int] = mapped_column(Integer)
    max_attempts: Mapped[int] = mapped_column(Integer)
    continuation_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    continuation_progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    timeout_seconds: Mapped[float] = mapped_column(Float)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    initiator_type: Mapped[str] = mapped_column(String(32))
    initiator_id: Mapped[str] = mapped_column(String(64))
    actor_snapshot: Mapped[dict[str, object]] = mapped_column(JSON)
    permission_set_version: Mapped[str] = mapped_column(String(96))
    required_permissions: Mapped[list[str]] = mapped_column(JSON)
    scope_type: Mapped[str] = mapped_column(String(48))
    scope_id: Mapped[str] = mapped_column(String(160))
    execution_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str] = mapped_column(String(96))
    run_id: Mapped[str] = mapped_column(String(96))
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class JobAttempt(JobsBase):
    __tablename__ = "job_attempts"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_no", name="uq_job_attempts_number"),
        Index("ix_job_attempts_job_id", "job_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("background_jobs.id", ondelete="CASCADE")
    )
    attempt_no: Mapped[int] = mapped_column(Integer)
    worker_id: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
