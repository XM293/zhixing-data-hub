"""Link every runtime turn to its AgentRun, MCP session, and trace context."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_agent_runtime_multiturn"
down_revision: str | None = "0046_agent_runtime_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runtime_turns") as batch:
        batch.add_column(sa.Column("agent_run_id", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("mcp_gateway_session_id", sa.String(64), nullable=True)
        )
        batch.add_column(sa.Column("request_id", sa.String(96), nullable=True))
        batch.add_column(sa.Column("run_id", sa.String(96), nullable=True))
        batch.create_foreign_key(
            "fk_agent_runtime_turns_agent_run",
            "agent_runs",
            ["agent_run_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_agent_runtime_turns_mcp_session",
            "mcp_gateway_sessions",
            ["mcp_gateway_session_id"],
            ["id"],
        )
        batch.create_index(
            "ix_agent_runtime_turns_agent_run_id",
            ["agent_run_id"],
        )
        batch.create_index(
            "ix_agent_runtime_turns_mcp_gateway_session_id",
            ["mcp_gateway_session_id"],
        )
        batch.create_index("ix_agent_runtime_turns_request_id", ["request_id"])
        batch.create_index("ix_agent_runtime_turns_run_id", ["run_id"])

    op.execute(
        sa.text(
            """
            UPDATE agent_runtime_turns
            SET agent_run_id = (
                    SELECT agent_run_id
                    FROM agent_runtime_sessions
                    WHERE agent_runtime_sessions.id = agent_runtime_turns.runtime_session_id
                ),
                mcp_gateway_session_id = (
                    SELECT mcp_gateway_session_id
                    FROM agent_runtime_sessions
                    WHERE agent_runtime_sessions.id = agent_runtime_turns.runtime_session_id
                ),
                request_id = (
                    SELECT request_id
                    FROM agent_runtime_sessions
                    WHERE agent_runtime_sessions.id = agent_runtime_turns.runtime_session_id
                ),
                run_id = (
                    SELECT run_id
                    FROM agent_runtime_sessions
                    WHERE agent_runtime_sessions.id = agent_runtime_turns.runtime_session_id
                )
            """
        )
    )

    with op.batch_alter_table("agent_runtime_turns") as batch:
        batch.alter_column(
            "agent_run_id",
            existing_type=sa.String(64),
            nullable=False,
        )
        batch.alter_column(
            "request_id",
            existing_type=sa.String(96),
            nullable=False,
        )
        batch.alter_column(
            "run_id",
            existing_type=sa.String(96),
            nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_runtime_turns") as batch:
        batch.drop_index("ix_agent_runtime_turns_run_id")
        batch.drop_index("ix_agent_runtime_turns_request_id")
        batch.drop_index("ix_agent_runtime_turns_mcp_gateway_session_id")
        batch.drop_index("ix_agent_runtime_turns_agent_run_id")
        batch.drop_constraint(
            "fk_agent_runtime_turns_mcp_session",
            type_="foreignkey",
        )
        batch.drop_constraint(
            "fk_agent_runtime_turns_agent_run",
            type_="foreignkey",
        )
        batch.drop_column("run_id")
        batch.drop_column("request_id")
        batch.drop_column("mcp_gateway_session_id")
        batch.drop_column("agent_run_id")
