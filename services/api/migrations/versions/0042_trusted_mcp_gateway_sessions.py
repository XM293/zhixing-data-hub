"""Add constrained trusted sessions and current authorization context for MCP tools."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0042_trusted_mcp_gateway_sessions"
down_revision: str | None = "0041_worker_authorization_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_gateway_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("user_account_id", sa.String(64), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("client_id", sa.String(120), nullable=False),
        sa.Column("session_token_hash", sa.String(128), nullable=False),
        sa.Column("allowed_tool_keys", sa.JSON(), nullable=False),
        sa.Column("scope_constraints", sa.JSON(), nullable=False),
        sa.Column("issued_permission_set_version", sa.String(120), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("agent_run_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_principal_id", sa.String(64), nullable=True),
        sa.Column("revoke_reason", sa.String(500), nullable=True),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["revoked_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("session_token_hash"),
    )
    _indexes(
        "mcp_gateway_sessions",
        "enterprise_id",
        "user_account_id",
        "principal_id",
        "client_id",
        "session_token_hash",
        "issued_permission_set_version",
        "agent_run_id",
        "status",
        "issued_at",
        "expires_at",
        "revoked_by_principal_id",
        "request_id",
        "run_id",
    )

    op.create_table(
        "mcp_gateway_session_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("gateway_session_id", sa.String(64), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("permission_set_version", sa.String(120), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["gateway_session_id"], ["mcp_gateway_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    _indexes(
        "mcp_gateway_session_events",
        "enterprise_id",
        "gateway_session_id",
        "actor_principal_id",
        "event_type",
        "request_id",
        "run_id",
        "occurred_at",
    )

    with op.batch_alter_table("tool_invocations") as batch_op:
        batch_op.add_column(sa.Column("gateway_session_id", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("agent_run_id", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("authentication_method", sa.String(48), nullable=True))
        batch_op.add_column(sa.Column("permission_set_version", sa.String(120), nullable=True))
        batch_op.add_column(
            sa.Column("session_permission_set_version", sa.String(120), nullable=True)
        )

    invocations = sa.table(
        "tool_invocations",
        sa.column("authentication_method", sa.String),
        sa.column("permission_set_version", sa.String),
    )
    op.get_bind().execute(
        sa.update(invocations).values(
            authentication_method="legacy-api",
            permission_set_version="legacy-unversioned",
        )
    )

    with op.batch_alter_table("tool_invocations") as batch_op:
        batch_op.alter_column(
            "authentication_method", existing_type=sa.String(48), nullable=False
        )
        batch_op.alter_column(
            "permission_set_version", existing_type=sa.String(120), nullable=False
        )
        batch_op.create_foreign_key(
            "fk_tool_invocations_gateway_session_id",
            "mcp_gateway_sessions",
            ["gateway_session_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_tool_invocations_agent_run_id",
            "agent_runs",
            ["agent_run_id"],
            ["id"],
        )
        batch_op.create_index(
            "ix_tool_invocations_gateway_session_id", ["gateway_session_id"]
        )
        batch_op.create_index("ix_tool_invocations_agent_run_id", ["agent_run_id"])
        batch_op.create_index(
            "ix_tool_invocations_authentication_method", ["authentication_method"]
        )
        batch_op.create_index(
            "ix_tool_invocations_permission_set_version", ["permission_set_version"]
        )


def downgrade() -> None:
    with op.batch_alter_table("tool_invocations") as batch_op:
        batch_op.drop_index("ix_tool_invocations_permission_set_version")
        batch_op.drop_index("ix_tool_invocations_authentication_method")
        batch_op.drop_index("ix_tool_invocations_agent_run_id")
        batch_op.drop_index("ix_tool_invocations_gateway_session_id")
        batch_op.drop_constraint("fk_tool_invocations_agent_run_id", type_="foreignkey")
        batch_op.drop_constraint("fk_tool_invocations_gateway_session_id", type_="foreignkey")
        batch_op.drop_column("session_permission_set_version")
        batch_op.drop_column("permission_set_version")
        batch_op.drop_column("authentication_method")
        batch_op.drop_column("agent_run_id")
        batch_op.drop_column("gateway_session_id")
    op.drop_table("mcp_gateway_session_events")
    op.drop_table("mcp_gateway_sessions")


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
