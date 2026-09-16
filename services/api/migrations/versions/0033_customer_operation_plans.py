"""Add governed, human-reviewed customer operation plan runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_customer_operation_plans"
down_revision: str | None = "0032_customer_360_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_operation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("customer_key", sa.String(160), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("execution_mode", sa.String(32), nullable=False),
        sa.Column("fallback_reason", sa.String(1000), nullable=True),
        sa.Column(
            "evidence_snapshot_id",
            sa.String(64),
            sa.ForeignKey("evidence_snapshots.id"),
            nullable=False,
        ),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column(
            "initiated_by_principal_id",
            sa.String(64),
            sa.ForeignKey("principals.id"),
            nullable=False,
        ),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "enterprise_id",
            "idempotency_key",
            name="uq_customer_operation_idempotency",
        ),
    )
    for column in (
        "enterprise_id",
        "customer_key",
        "scope_type",
        "scope_key",
        "status",
        "risk_level",
        "execution_mode",
        "evidence_snapshot_id",
        "initiated_by_principal_id",
        "idempotency_key",
        "request_id",
        "run_id",
        "created_at",
        "completed_at",
    ):
        op.create_index(
            f"ix_customer_operation_runs_{column}",
            "customer_operation_runs",
            [column],
        )


def downgrade() -> None:
    op.drop_table("customer_operation_runs")
