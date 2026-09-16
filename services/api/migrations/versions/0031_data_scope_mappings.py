"""Add versioned mappings from platform scopes to source business keys."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_data_scope_mappings"
down_revision: str | None = "0030_canonical_commerce_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_scope_mappings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "external_system_id",
            sa.String(64),
            sa.ForeignKey("external_systems.id"),
            nullable=False,
        ),
        sa.Column("sync_run_id", sa.String(64), sa.ForeignKey("sync_runs.id"), nullable=False),
        sa.Column("scope_type", sa.String(48), nullable=False),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("external_scope_key", sa.String(160), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("source_schema_version", sa.String(64), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "enterprise_id",
            "external_system_id",
            "scope_type",
            "external_scope_key",
            name="uq_data_scope_mapping_source_key",
        ),
    )
    for column in (
        "enterprise_id",
        "external_system_id",
        "sync_run_id",
        "scope_type",
        "scope_key",
        "external_scope_key",
        "status",
    ):
        op.create_index(
            f"ix_data_scope_mappings_{column}",
            "data_scope_mappings",
            [column],
        )


def downgrade() -> None:
    op.drop_table("data_scope_mappings")
