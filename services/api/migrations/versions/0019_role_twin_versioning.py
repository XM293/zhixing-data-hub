"""Add immutable role templates and role twin configuration versions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_role_twin_versioning"
down_revision: str | None = "0018_agent_memory_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_templates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("template_key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint("enterprise_id", "template_key"),
    )
    for column in ("enterprise_id", "status"):
        op.create_index(f"ix_role_templates_{column}", "role_templates", [column])

    op.create_table(
        "role_template_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("role_title", sa.String(160), nullable=False),
        sa.Column("responsibilities", sa.JSON(), nullable=False),
        sa.Column("capability_boundaries", sa.JSON(), nullable=False),
        sa.Column("default_voice_guide", sa.Text(), nullable=False),
        sa.Column("default_reasoning_guide", sa.Text(), nullable=False),
        sa.Column("default_answer_policy", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.String(1000), nullable=False),
        sa.Column("created_by_principal_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["template_id"], ["role_templates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("template_id", "version_number"),
    )
    for column in ("template_id", "status", "created_by_principal_id"):
        op.create_index(
            f"ix_role_template_versions_{column}", "role_template_versions", [column]
        )

    with op.batch_alter_table("role_twin_profiles") as batch_op:
        batch_op.add_column(sa.Column("role_template_id", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("owner_principal_id", sa.String(64), nullable=True))
        batch_op.create_foreign_key(
            "fk_role_twin_profiles_template",
            "role_templates",
            ["role_template_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_role_twin_profiles_owner",
            "principals",
            ["owner_principal_id"],
            ["id"],
        )
        batch_op.create_index("ix_role_twin_profiles_role_template_id", ["role_template_id"])
        batch_op.create_index("ix_role_twin_profiles_owner_principal_id", ["owner_principal_id"])

    op.create_table(
        "role_twin_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("twin_profile_id", sa.String(64), nullable=False),
        sa.Column("template_version_id", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("voice_guide", sa.Text(), nullable=False),
        sa.Column("reasoning_guide", sa.Text(), nullable=False),
        sa.Column("answer_policy", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.String(1000), nullable=False),
        sa.Column("created_by_principal_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["twin_profile_id"], ["role_twin_profiles.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["template_version_id"], ["role_template_versions.id"]),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("twin_profile_id", "version_number"),
    )
    for column in (
        "twin_profile_id",
        "template_version_id",
        "status",
        "created_by_principal_id",
    ):
        op.create_index(f"ix_role_twin_versions_{column}", "role_twin_versions", [column])

    op.create_table(
        "role_configuration_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("configuration_type", sa.String(32), nullable=False),
        sa.Column("configuration_key", sa.String(100), nullable=False),
        sa.Column("version_id", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    for column in (
        "enterprise_id",
        "actor_principal_id",
        "configuration_type",
        "configuration_key",
        "version_id",
        "event_type",
        "request_id",
        "run_id",
        "occurred_at",
    ):
        op.create_index(
            f"ix_role_configuration_events_{column}", "role_configuration_events", [column]
        )

    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("role_twin_version_id", sa.String(64), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_runs_role_twin_version",
            "role_twin_versions",
            ["role_twin_version_id"],
            ["id"],
        )
        batch_op.create_index("ix_agent_runs_role_twin_version_id", ["role_twin_version_id"])


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_index("ix_agent_runs_role_twin_version_id")
        batch_op.drop_constraint("fk_agent_runs_role_twin_version", type_="foreignkey")
        batch_op.drop_column("role_twin_version_id")
    op.drop_table("role_configuration_events")
    op.drop_table("role_twin_versions")
    with op.batch_alter_table("role_twin_profiles") as batch_op:
        batch_op.drop_index("ix_role_twin_profiles_owner_principal_id")
        batch_op.drop_index("ix_role_twin_profiles_role_template_id")
        batch_op.drop_constraint("fk_role_twin_profiles_owner", type_="foreignkey")
        batch_op.drop_constraint("fk_role_twin_profiles_template", type_="foreignkey")
        batch_op.drop_column("owner_principal_id")
        batch_op.drop_column("role_template_id")
    op.drop_table("role_template_versions")
    op.drop_table("role_templates")
