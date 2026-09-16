"""Persist the enterprise tool registry and invocation audit ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_enterprise_tool_gateway"
down_revision: str | None = "0014_identity_access_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_definitions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("tool_key", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(800), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("permission_key", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("scope_resolver", sa.String(120), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint("enterprise_id", "tool_key", "version"),
    )
    _indexes(
        "tool_definitions",
        "enterprise_id",
        "tool_key",
        "risk_level",
        "permission_key",
        "status",
    )

    op.create_table(
        "tool_invocations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("tool_definition_id", sa.String(64), nullable=False),
        sa.Column("tool_key", sa.String(120), nullable=False),
        sa.Column("tool_version", sa.String(32), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("input_parameters", sa.JSON(), nullable=False),
        sa.Column("output_summary", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["tool_definition_id"], ["tool_definitions.id"]),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    _indexes(
        "tool_invocations",
        "enterprise_id",
        "tool_definition_id",
        "tool_key",
        "actor_principal_id",
        "request_id",
        "run_id",
        "status",
        "started_at",
    )


def downgrade() -> None:
    op.drop_table("tool_invocations")
    op.drop_table("tool_definitions")


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
