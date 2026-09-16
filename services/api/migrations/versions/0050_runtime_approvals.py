"""Persist Codex Runtime approval requests."""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0050_runtime_approvals"
down_revision: str | None = "0049_skill_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runtime_approvals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("runtime_session_id", sa.String(64), nullable=False),
        sa.Column("runtime_turn_id", sa.String(64), nullable=True),
        sa.Column("agent_run_id", sa.String(64), nullable=False),
        sa.Column("request_method", sa.String(120), nullable=False),
        sa.Column("item_id", sa.String(160), nullable=True),
        sa.Column("skill_key", sa.String(100), nullable=True),
        sa.Column("skill_version", sa.Integer(), nullable=True),
        sa.Column("tool_keys", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(32), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_principal_id", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["runtime_session_id"], ["agent_runtime_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_principal_id"], ["principals.id"]),
    )
    for column in ("enterprise_id", "runtime_session_id", "agent_run_id", "status", "requested_at"):
        op.create_index(f"ix_agent_runtime_approvals_{column}", "agent_runtime_approvals", [column])


def downgrade() -> None:
    op.drop_table("agent_runtime_approvals")
