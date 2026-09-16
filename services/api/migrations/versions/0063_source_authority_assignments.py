"""Explicit source authority per project; legacy rules are preserved without inference."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0063_source_authority_assignments"
down_revision = "0062_canonical_after_sales"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("source_authority_assignments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("business_unit_id", sa.String(64), sa.ForeignKey("business_units.id"),
                  nullable=False),
        sa.Column("external_system_id", sa.String(64), sa.ForeignKey("external_systems.id"),
                  nullable=False),
        sa.Column("fact_family", sa.String(80), nullable=False),
        sa.Column("resource_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enterprise_id", "business_unit_id", "fact_family"))
    for key in ("enterprise_id", "business_unit_id", "external_system_id"):
        op.create_index(f"ix_source_authority_assignments_{key}", "source_authority_assignments",
                        [key])


def downgrade() -> None:
    op.drop_table("source_authority_assignments")
