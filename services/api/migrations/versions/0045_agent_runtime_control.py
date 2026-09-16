"""Add Codex app-server runtime probe audit."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_agent_runtime_control"
down_revision: str | None = "0044_platform_management_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runtime_probe_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("runtime_key", sa.String(64), nullable=False),
        sa.Column("protocol", sa.String(64), nullable=False),
        sa.Column("command_version", sa.String(160), nullable=True),
        sa.Column("initialized", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
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
        "runtime_key",
        "status",
        "request_id",
        "run_id",
        "created_at",
    ):
        op.create_index(
            f"ix_agent_runtime_probe_runs_{column}",
            "agent_runtime_probe_runs",
            [column],
        )


def downgrade() -> None:
    op.drop_table("agent_runtime_probe_runs")
