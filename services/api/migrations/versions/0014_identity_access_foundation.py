"""Persist enterprise identity, access roles, scopes, and authorization decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_identity_access_foundation"
down_revision: str | None = "0013_action_confirmation_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "principals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("principal_key", sa.String(120), nullable=False),
        sa.Column("principal_type", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint("enterprise_id", "principal_key"),
    )
    _indexes("principals", "enterprise_id", "principal_key", "principal_type", "status")

    op.create_table(
        "user_accounts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("account_key", sa.String(120), nullable=False),
        sa.Column("local_login_name", sa.String(120), nullable=False),
        sa.Column("experience_role_key", sa.String(48), nullable=False),
        sa.Column("email", sa.String(240), nullable=True),
        sa.Column("authentication_source", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "account_key"),
        sa.UniqueConstraint("enterprise_id", "local_login_name"),
        sa.UniqueConstraint("principal_id"),
    )
    _indexes(
        "user_accounts",
        "enterprise_id",
        "principal_id",
        "account_key",
        "local_login_name",
        "experience_role_key",
        "status",
    )

    op.create_table(
        "org_units",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("org_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("unit_type", sa.String(48), nullable=False),
        sa.Column("parent_org_unit_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["parent_org_unit_id"], ["org_units.id"]),
        sa.UniqueConstraint("enterprise_id", "org_key"),
    )
    _indexes("org_units", "enterprise_id", "org_key", "unit_type", "parent_org_unit_id", "status")

    op.create_table(
        "positions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("org_unit_id", sa.String(64), nullable=False),
        sa.Column("position_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("position_level", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["org_unit_id"], ["org_units.id"]),
        sa.UniqueConstraint("enterprise_id", "position_key"),
    )
    _indexes("positions", "enterprise_id", "org_unit_id", "position_key", "status")

    op.create_table(
        "memberships",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("org_unit_id", sa.String(64), nullable=False),
        sa.Column("position_id", sa.String(64), nullable=False),
        sa.Column("membership_type", sa.String(32), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["org_unit_id"], ["org_units.id"]),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"]),
        sa.UniqueConstraint("enterprise_id", "principal_id", "org_unit_id", "position_id"),
    )
    _indexes("memberships", "enterprise_id", "principal_id", "org_unit_id", "position_id", "status")

    op.create_table(
        "permission_definitions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("permission_key", sa.String(120), nullable=False, unique=True),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("resource", sa.String(80), nullable=False),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
    )
    _indexes("permission_definitions", "permission_key", "resource", "risk_level", "status")

    op.create_table(
        "access_roles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("role_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint("enterprise_id", "role_key", "version"),
    )
    _indexes("access_roles", "enterprise_id", "role_key", "status")

    op.create_table(
        "access_role_permissions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("access_role_id", sa.String(64), nullable=False),
        sa.Column("permission_id", sa.String(64), nullable=False),
        sa.Column("effect", sa.String(16), nullable=False),
        sa.ForeignKeyConstraint(["access_role_id"], ["access_roles.id"]),
        sa.ForeignKeyConstraint(["permission_id"], ["permission_definitions.id"]),
        sa.UniqueConstraint("access_role_id", "permission_id"),
    )
    _indexes("access_role_permissions", "access_role_id", "permission_id")

    op.create_table(
        "role_assignments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("access_role_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["access_role_id"], ["access_roles.id"]),
        sa.UniqueConstraint("enterprise_id", "principal_id", "access_role_id"),
    )
    _indexes("role_assignments", "enterprise_id", "principal_id", "access_role_id", "status")

    op.create_table(
        "scope_grants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("role_assignment_id", sa.String(64), nullable=False),
        sa.Column("scope_type", sa.String(48), nullable=False),
        sa.Column("scope_ids", sa.JSON(), nullable=False),
        sa.Column("effect", sa.String(16), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["role_assignment_id"], ["role_assignments.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("role_assignment_id", "scope_type"),
    )
    _indexes("scope_grants", "enterprise_id", "role_assignment_id", "scope_type")

    op.create_table(
        "authorization_decisions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("permission_key", sa.String(120), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_key", sa.String(200), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(240), nullable=False),
        sa.Column("policy_version", sa.String(120), nullable=False),
        sa.Column("scope_snapshot", sa.JSON(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    _indexes(
        "authorization_decisions",
        "enterprise_id",
        "request_id",
        "run_id",
        "actor_principal_id",
        "permission_key",
        "resource_type",
        "resource_key",
        "decision",
        "decided_at",
    )


def downgrade() -> None:
    op.drop_table("authorization_decisions")
    op.drop_table("scope_grants")
    op.drop_table("role_assignments")
    op.drop_table("access_role_permissions")
    op.drop_table("access_roles")
    op.drop_table("permission_definitions")
    op.drop_table("memberships")
    op.drop_table("positions")
    op.drop_table("org_units")
    op.drop_table("user_accounts")
    op.drop_table("principals")


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
