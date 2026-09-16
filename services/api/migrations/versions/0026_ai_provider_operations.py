"""Add privacy-preserving AI provider probes and operational audit records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_ai_provider_operations"
down_revision: str | None = "0025_customer_service_copilot"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_probe_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("protocol", sa.String(64), nullable=False),
        sa.Column("structured_output_supported", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    for column in (
        "enterprise_id",
        "actor_principal_id",
        "provider_key",
        "model",
        "status",
        "request_id",
        "run_id",
        "created_at",
    ):
        op.create_index(
            f"ix_ai_provider_probe_runs_{column}",
            "ai_provider_probe_runs",
            [column],
        )


def downgrade() -> None:
    op.drop_table("ai_provider_probe_runs")
