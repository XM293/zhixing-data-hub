"""Add enterprise skill registry and immutable versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0049_skill_registry"
down_revision: str | None = "0048_enterprise_scope_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_skills",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("skill_key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=True),
        sa.Column("created_by_principal_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "skill_key"),
    )
    for column in (
        "enterprise_id",
        "skill_key",
        "status",
        "current_version_number",
        "created_at",
    ):
        op.create_index(f"ix_agent_skills_{column}", "agent_skills", [column])

    op.create_table(
        "agent_skill_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("skill_id", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("tool_keys", sa.JSON(), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.String(1000), nullable=False),
        sa.Column("created_by_principal_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["skill_id"], ["agent_skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("skill_id", "version_number"),
    )
    for column in (
        "enterprise_id",
        "skill_id",
        "version_number",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_agent_skill_versions_{column}",
            "agent_skill_versions",
            [column],
        )

    op.create_table(
        "agent_skill_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("skill_id", sa.String(64), nullable=False),
        sa.Column("version_id", sa.String(64), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["skill_id"], ["agent_skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["agent_skill_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    for column in (
        "enterprise_id",
        "skill_id",
        "version_id",
        "actor_principal_id",
        "event_type",
        "occurred_at",
    ):
        op.create_index(
            f"ix_agent_skill_events_{column}",
            "agent_skill_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("agent_skill_events")
    op.drop_table("agent_skill_versions")
    op.drop_table("agent_skills")
