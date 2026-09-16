"""Add paused-by-default source schedules and batch command identity."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0061_source_sync_schedules"
down_revision = "0060_source_request_budgets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("sync_runs", sa.Column("command_fingerprint", sa.String(64), nullable=True))
    op.create_table("source_sync_schedules",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("external_system_id", sa.String(64), sa.ForeignKey("external_systems.id"),
                  nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("resource_key", sa.String(120), nullable=False),
        sa.Column("strategy", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="paused"),
        *(sa.Column(key, sa.Integer(), nullable=False) for key in
          ("interval_seconds", "overlap_seconds", "safety_lag_seconds", "reconcile_days")),
        *(sa.Column(key, sa.DateTime(timezone=True), nullable=True) for key in
          ("initial_start", "watermark", "pending_end", "last_success_at", "last_reconciled_at")),
        sa.Column("active_run_id", sa.String(64), sa.ForeignKey("sync_runs.id"), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pending_reconciliation", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("scope_snapshot", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    for key in ("enterprise_id", "external_system_id", "status", "next_run_at"):
        op.create_index(f"ix_source_sync_schedules_{key}", "source_sync_schedules", [key])


def downgrade() -> None:
    op.drop_table("source_sync_schedules")
    op.drop_column("sync_runs", "command_fingerprint")
