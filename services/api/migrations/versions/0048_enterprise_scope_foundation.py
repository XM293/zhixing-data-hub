"""Add group, business-unit and multi-enterprise scope foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_enterprise_scope_foundation"
down_revision: str | None = "0047_agent_runtime_multiturn"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enterprise_groups",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_enterprise_groups_code"),
    )
    op.create_index("ix_enterprise_groups_code", "enterprise_groups", ["code"], unique=True)
    op.create_index("ix_enterprise_groups_status", "enterprise_groups", ["status"])

    op.create_table(
        "business_units",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("unit_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("unit_type", sa.String(48), nullable=False),
        sa.Column("parent_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["business_units.id"]),
        sa.UniqueConstraint("enterprise_id", "unit_key", name="uq_business_units_enterprise_key"),
    )
    op.create_index("ix_business_units_enterprise_id", "business_units", ["enterprise_id"])
    op.create_index("ix_business_units_unit_key", "business_units", ["unit_key"])
    op.create_index("ix_business_units_unit_type", "business_units", ["unit_type"])
    op.create_index("ix_business_units_parent_id", "business_units", ["parent_id"])
    op.create_index("ix_business_units_status", "business_units", ["status"])

    op.create_table(
        "enterprise_memberships",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("membership_type", sa.String(32), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint(
            "principal_id", "enterprise_id", name="uq_enterprise_memberships_principal"
        ),
    )
    op.create_index(
        "ix_enterprise_memberships_principal_id", "enterprise_memberships", ["principal_id"]
    )
    op.create_index(
        "ix_enterprise_memberships_enterprise_id", "enterprise_memberships", ["enterprise_id"]
    )
    op.create_index(
        "ix_enterprise_memberships_membership_type", "enterprise_memberships", ["membership_type"]
    )
    op.create_index(
        "ix_enterprise_memberships_status", "enterprise_memberships", ["status"]
    )

    op.create_table(
        "enterprise_scope_grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("group_id", sa.String(64), nullable=True),
        sa.Column("enterprise_id", sa.String(64), nullable=True),
        sa.Column("scope_type", sa.String(48), nullable=False),
        sa.Column("scope_id", sa.String(160), nullable=False),
        sa.Column("effect", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["enterprise_groups.id"]),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint(
            "principal_id", "scope_type", "scope_id", name="uq_enterprise_scope_grant_target"
        ),
    )
    for column in ("principal_id", "group_id", "enterprise_id", "scope_type", "scope_id", "status"):
        op.create_index(
            f"ix_enterprise_scope_grants_{column}", "enterprise_scope_grants", [column]
        )

    op.create_table(
        "consolidation_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("group_id", sa.String(64), nullable=False),
        sa.Column("profile_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("base_currency", sa.String(16), nullable=False),
        sa.Column("elimination_rules", sa.JSON, nullable=False),
        sa.Column("exchange_rate_policy", sa.JSON, nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["enterprise_groups.id"]),
        sa.UniqueConstraint(
            "group_id", "profile_key", "version", name="uq_consolidation_profiles_key"
        ),
    )
    op.create_index("ix_consolidation_profiles_group_id", "consolidation_profiles", ["group_id"])
    op.create_index(
        "ix_consolidation_profiles_profile_key", "consolidation_profiles", ["profile_key"]
    )
    op.create_index("ix_consolidation_profiles_status", "consolidation_profiles", ["status"])

    op.create_table(
        "center_assignments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("group_id", sa.String(64), nullable=True),
        sa.Column("enterprise_id", sa.String(64), nullable=True),
        sa.Column("scope_type", sa.String(48), nullable=False),
        sa.Column("scope_id", sa.String(160), nullable=False),
        sa.Column("center_key", sa.String(120), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("owner_principal_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["enterprise_groups.id"]),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["owner_principal_id"], ["principals.id"]),
        sa.UniqueConstraint(
            "scope_type", "scope_id", "center_key", name="uq_center_assignments_target"
        ),
    )
    for column in (
        "group_id",
        "enterprise_id",
        "scope_type",
        "scope_id",
        "center_key",
        "owner_principal_id",
    ):
        op.create_index(f"ix_center_assignments_{column}", "center_assignments", [column])
    op.create_index("ix_center_assignments_enabled", "center_assignments", ["enabled"])
    op.create_index("ix_center_assignments_updated_at", "center_assignments", ["updated_at"])

    op.create_table(
        "source_bindings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("business_unit_id", sa.String(64), nullable=True),
        sa.Column("source_system_id", sa.String(64), nullable=False),
        sa.Column("external_key", sa.String(200), nullable=False),
        sa.Column("canonical_type", sa.String(64), nullable=False),
        sa.Column("canonical_id", sa.String(200), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["business_unit_id"], ["business_units.id"]),
        sa.UniqueConstraint(
            "enterprise_id",
            "source_system_id",
            "external_key",
            name="uq_source_bindings_external_key",
        ),
    )
    for column in (
        "enterprise_id",
        "business_unit_id",
        "source_system_id",
        "external_key",
        "canonical_type",
        "canonical_id",
        "status",
    ):
        op.create_index(f"ix_source_bindings_{column}", "source_bindings", [column])
    op.create_index("ix_source_bindings_updated_at", "source_bindings", ["updated_at"])

    with op.batch_alter_table("enterprises") as batch:
        batch.add_column(sa.Column("group_id", sa.String(64), nullable=True))
        batch.create_foreign_key(
            "fk_enterprises_group_id", "enterprise_groups", ["group_id"], ["id"]
        )
        batch.create_index("ix_enterprises_group_id", ["group_id"])

    # Existing single-enterprise installations are promoted into a deterministic
    # one-enterprise group without changing their current authorization behavior.
    op.execute(
        sa.text(
            """
            INSERT INTO enterprise_groups
                (id, code, name, status, timezone, created_at, updated_at)
            SELECT 'grp_' || e.id, 'GROUP-' || e.code, e.name, 'active', e.timezone,
                   e.created_at, e.created_at
            FROM enterprises e
            WHERE NOT EXISTS (
                SELECT 1 FROM enterprise_groups g WHERE g.id = 'grp_' || e.id
            )
            """
        )
    )
    op.execute(sa.text("UPDATE enterprises SET group_id = 'grp_' || id WHERE group_id IS NULL"))


def downgrade() -> None:
    with op.batch_alter_table("enterprises") as batch:
        batch.drop_index("ix_enterprises_group_id")
        batch.drop_constraint("fk_enterprises_group_id", type_="foreignkey")
        batch.drop_column("group_id")

    for table in (
        "source_bindings",
        "center_assignments",
        "consolidation_profiles",
        "enterprise_scope_grants",
        "enterprise_memberships",
        "business_units",
        "enterprise_groups",
    ):
        op.drop_table(table)
