"""Create the PostgreSQL-backed background job foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_background_jobs"
down_revision: str | None = "0006_seed_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "background_jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("job_type", sa.String(120), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("initiator_type", sa.String(32), nullable=False),
        sa.Column("initiator_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("worker_id", sa.String(120), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("last_error_code", sa.String(120), nullable=True),
        sa.Column("last_error_message", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint(
            "enterprise_id",
            "job_type",
            "idempotency_key",
            name="uq_background_jobs_idempotency",
        ),
    )
    op.create_index("ix_background_jobs_enterprise_id", "background_jobs", ["enterprise_id"])
    op.create_index("ix_background_jobs_run_id", "background_jobs", ["run_id"])
    op.create_index(
        "ix_background_jobs_claim",
        "background_jobs",
        ["status", "available_at", "priority", "created_at"],
    )
    op.create_index(
        "ix_background_jobs_lease",
        "background_jobs",
        ["status", "lease_expires_at"],
    )

    op.create_table(
        "job_attempts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("job_id", sa.String(64), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["background_jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("job_id", "attempt_no", name="uq_job_attempts_number"),
    )
    op.create_index("ix_job_attempts_job_id", "job_attempts", ["job_id"])


def downgrade() -> None:
    op.drop_table("job_attempts")
    op.drop_table("background_jobs")
