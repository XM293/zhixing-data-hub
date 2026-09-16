"""Persist agent runtime sessions, turns, and normalized events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_agent_runtime_sessions"
down_revision: str | None = "0045_agent_runtime_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_runtime_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("agent_run_id", sa.String(64), nullable=False),
        sa.Column("runtime_key", sa.String(64), nullable=False),
        sa.Column("runtime_thread_id", sa.String(160), nullable=False),
        sa.Column("runtime_session_id", sa.String(160), nullable=True),
        sa.Column("mcp_gateway_session_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_event_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_code", sa.String(120), nullable=True),
        sa.Column("failure_message", sa.String(500), nullable=True),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["mcp_gateway_session_id"],
            ["mcp_gateway_sessions.id"],
        ),
        sa.UniqueConstraint("agent_run_id", name="uq_agent_runtime_sessions_agent_run"),
    )
    for column in (
        "enterprise_id",
        "runtime_key",
        "runtime_thread_id",
        "runtime_session_id",
        "mcp_gateway_session_id",
        "status",
        "request_id",
        "run_id",
        "created_at",
    ):
        op.create_index(
            f"ix_agent_runtime_sessions_{column}",
            "agent_runtime_sessions",
            [column],
        )

    op.create_table(
        "agent_runtime_turns",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("runtime_session_id", sa.String(64), nullable=False),
        sa.Column("runtime_turn_id", sa.String(160), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("model", sa.String(120), nullable=True),
        sa.Column("failure_code", sa.String(120), nullable=True),
        sa.Column("failure_message", sa.String(500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_session_id"],
            ["agent_runtime_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "runtime_session_id",
            "turn_number",
            name="uq_agent_runtime_turns_number",
        ),
        sa.UniqueConstraint(
            "runtime_session_id",
            "runtime_turn_id",
            name="uq_agent_runtime_turns_runtime_id",
        ),
    )
    for column in (
        "enterprise_id",
        "runtime_session_id",
        "runtime_turn_id",
        "status",
        "started_at",
    ):
        op.create_index(
            f"ix_agent_runtime_turns_{column}",
            "agent_runtime_turns",
            [column],
        )

    op.create_table(
        "agent_runtime_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("runtime_session_id", sa.String(64), nullable=False),
        sa.Column("runtime_turn_id", sa.String(64), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("runtime_sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("event_payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["runtime_session_id"],
            ["agent_runtime_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["runtime_turn_id"],
            ["agent_runtime_turns.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "runtime_session_id",
            "sequence",
            name="uq_agent_runtime_events_sequence",
        ),
    )
    for column in (
        "enterprise_id",
        "runtime_session_id",
        "runtime_turn_id",
        "event_type",
        "status",
        "occurred_at",
    ):
        op.create_index(
            f"ix_agent_runtime_events_{column}",
            "agent_runtime_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("agent_runtime_events")
    op.drop_table("agent_runtime_turns")
    op.drop_table("agent_runtime_sessions")
