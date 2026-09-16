"""Persist bounded, scope-aware values used by dependent read-only resources."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0075_source_dependency_values"
down_revision = "0074_backfill_window_contract"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_dependency_values",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64),
                  sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("external_system_id", sa.String(64),
                  sa.ForeignKey("external_systems.id"), nullable=False),
        sa.Column("source_resource_id", sa.String(64),
                  sa.ForeignKey("source_resources.id"), nullable=False),
        sa.Column("first_manifest_id", sa.String(64),
                  sa.ForeignKey("raw_page_manifests.id"), nullable=False),
        sa.Column("last_manifest_id", sa.String(64),
                  sa.ForeignKey("raw_page_manifests.id"), nullable=False),
        sa.Column("business_unit_id", sa.String(64),
                  sa.ForeignKey("business_units.id"), nullable=True),
        sa.Column("value_type", sa.String(64), nullable=False),
        sa.Column("external_value", sa.String(300), nullable=False),
        sa.Column("value_hash", sa.String(64), nullable=False),
        sa.Column("scope_kind", sa.String(32), nullable=False,
                  server_default="source"),
        sa.Column("scope_external_key", sa.String(200), nullable=False,
                  server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurrence_count", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("extractor_version", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "external_system_id", "value_type", "value_hash", "scope_kind",
            "scope_external_key", name="uq_source_dependency_value_identity"),
        sa.CheckConstraint("occurrence_count >= 1",
                           name="ck_source_dependency_occurrence_count"),
        sa.CheckConstraint("status IN ('active','stale','rejected')",
                           name="ck_source_dependency_status"),
    )
    for column in (
        "enterprise_id", "external_system_id", "source_resource_id",
        "business_unit_id", "value_type", "status", "last_seen_at",
    ):
        op.create_index(
            f"ix_source_dependency_values_{column}", "source_dependency_values", [column])


def downgrade() -> None:
    op.drop_table("source_dependency_values")
