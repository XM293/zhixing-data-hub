"""Add read-only sales outbound headers and stable source lines."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0065_canonical_fulfillments"
down_revision = "0064_job_continuations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "canonical_fulfillments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("external_system_id", sa.String(64), sa.ForeignKey("external_systems.id"),
                  nullable=False),
        sa.Column("business_unit_id", sa.String(64), sa.ForeignKey("business_units.id")),
        sa.Column("raw_manifest_id", sa.String(64), sa.ForeignKey("raw_page_manifests.id"),
                  nullable=False),
        sa.Column("resource_key", sa.String(120), nullable=False),
        sa.Column("external_key", sa.String(200), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("store_key", sa.String(160), nullable=False),
        sa.Column("warehouse_key", sa.String(160), nullable=False),
        sa.Column("shipment_number", sa.String(200), nullable=False),
        sa.Column("order_external_key", sa.String(200), nullable=False),
        sa.Column("platform_order_keys", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("logistics_status", sa.Integer(), nullable=False),
        sa.Column("freight_amount", sa.Numeric(38, 12)),
        sa.Column("freight_currency_code", sa.String(8)),
        sa.Column("base_freight_amount", sa.Numeric(38, 12)),
        sa.Column("base_currency_code", sa.String(8)),
        sa.Column("exchange_rate_version", sa.String(64)),
        sa.Column("source_local_time", sa.String(64), nullable=False),
        sa.Column("source_updated_local_time", sa.String(64), nullable=False),
        sa.Column("dispatched_local_time", sa.String(64)),
        sa.Column("source_timezone", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("dispatched_at", sa.DateTime(timezone=True)),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.UniqueConstraint("external_system_id", "resource_key", "external_key"),
    )
    op.create_table(
        "canonical_fulfillment_lines",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("fulfillment_id", sa.String(64), sa.ForeignKey("canonical_fulfillments.id"),
                  nullable=False),
        sa.Column("external_key", sa.String(200), nullable=False),
        sa.Column("product_external_key", sa.String(200), nullable=False),
        sa.Column("sku", sa.String(160), nullable=False),
        sa.Column("quantity", sa.BigInteger(), nullable=False),
        sa.Column("bundle_type", sa.Integer(), nullable=False),
        sa.Column("parent_external_key", sa.String(200)),
        sa.UniqueConstraint("fulfillment_id", "external_key"),
    )
    for column in ("enterprise_id", "external_system_id", "business_unit_id", "raw_manifest_id",
                   "store_key", "warehouse_key", "order_external_key", "status", "business_date"):
        op.create_index(f"ix_canonical_fulfillments_{column}", "canonical_fulfillments", [column])
    op.create_index("ix_canonical_fulfillment_lines_fulfillment_id", "canonical_fulfillment_lines",
                    ["fulfillment_id"])


def downgrade() -> None:
    op.drop_table("canonical_fulfillment_lines")
    op.drop_table("canonical_fulfillments")
