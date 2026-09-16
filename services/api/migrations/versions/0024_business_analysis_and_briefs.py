"""Add persisted metric-backed business analysis runs and briefs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_business_analysis_and_briefs"
down_revision: str | None = "0023_feedback_evaluation_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_analysis_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("analysis_type", sa.String(48), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("scope_label", sa.String(200), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("execution_mode", sa.String(32), nullable=False),
        sa.Column("fallback_reason", sa.String(1000), nullable=True),
        sa.Column("evidence_snapshot_id", sa.String(64), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("initiated_by_principal_id", sa.String(64), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["evidence_snapshot_id"], ["evidence_snapshots.id"]),
        sa.ForeignKeyConstraint(["initiated_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    for column in (
        "enterprise_id", "analysis_type", "scope_type", "scope_key", "status",
        "risk_level", "execution_mode", "evidence_snapshot_id",
        "initiated_by_principal_id", "idempotency_key", "request_id", "run_id",
        "created_at", "completed_at",
    ):
        op.create_index(
            f"ix_business_analysis_runs_{column}", "business_analysis_runs", [column]
        )

    op.create_table(
        "business_briefs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("brief_key", sa.String(160), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("brief_type", sa.String(32), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("scope_label", sa.String(200), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_analysis_run_id", sa.String(64), nullable=False),
        sa.Column("evidence_snapshot_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("execution_mode", sa.String(32), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("created_by_principal_id", sa.String(64), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["source_analysis_run_id"], ["business_analysis_runs.id"]),
        sa.ForeignKeyConstraint(["evidence_snapshot_id"], ["evidence_snapshots.id"]),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "brief_key", "version_number"),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    for column in (
        "enterprise_id", "brief_key", "brief_type", "scope_type", "scope_key",
        "status", "source_analysis_run_id", "evidence_snapshot_id", "execution_mode",
        "created_by_principal_id", "idempotency_key", "request_id", "run_id", "created_at",
    ):
        op.create_index(f"ix_business_briefs_{column}", "business_briefs", [column])


def downgrade() -> None:
    op.drop_table("business_briefs")
    op.drop_table("business_analysis_runs")
