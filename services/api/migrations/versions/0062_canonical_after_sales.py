"""Preserve child after-sale identity, source money and uncertain local timestamps."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0062_canonical_after_sales"
down_revision = "0061_source_sync_schedules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("canonical_after_sales",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("external_system_id", sa.String(64), sa.ForeignKey("external_systems.id"),
                  nullable=False),
        sa.Column("business_unit_id", sa.String(64), sa.ForeignKey("business_units.id"),
                  nullable=True),
        sa.Column("raw_manifest_id", sa.String(64), sa.ForeignKey("raw_page_manifests.id"),
                  nullable=False),
        sa.Column("resource_key", sa.String(120), nullable=False),
        sa.Column("external_key", sa.String(200), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_item_key", sa.Text(), nullable=False),
        sa.Column("store_key", sa.String(160), nullable=False),
        sa.Column("order_external_key", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(160), nullable=False),
        sa.Column("after_type", sa.String(32), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(64), nullable=True),
        sa.Column("source_amount_text", sa.String(200), nullable=False),
        sa.Column("amount", sa.Numeric(38, 12), nullable=True),
        sa.Column("currency_code", sa.String(8), nullable=True),
        sa.Column("base_amount", sa.Numeric(38, 12), nullable=True),
        sa.Column("base_currency_code", sa.String(8), nullable=True),
        sa.Column("exchange_rate_version", sa.String(64), nullable=True),
        sa.Column("source_local_time", sa.String(64), nullable=False),
        sa.Column("source_updated_local_time", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("store_timezone", sa.String(64), nullable=True),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.UniqueConstraint("external_system_id", "resource_key", "external_key"))
    for key in ("enterprise_id", "external_system_id", "business_unit_id", "raw_manifest_id",
                "store_key", "order_external_key", "after_type", "business_date"):
        op.create_index(f"ix_canonical_after_sales_{key}", "canonical_after_sales", [key])


def downgrade() -> None:
    op.drop_table("canonical_after_sales")
