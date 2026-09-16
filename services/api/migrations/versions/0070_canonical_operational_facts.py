"""Add a governed canonical envelope for remaining W0-W3 operational facts."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0070_canonical_operational_facts"
down_revision = "0069_raw_request_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "canonical_operational_facts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"),
                  nullable=False),
        sa.Column("external_system_id", sa.String(64), sa.ForeignKey("external_systems.id"),
                  nullable=False),
        sa.Column("resource_key", sa.String(120), nullable=False),
        sa.Column("external_key", sa.String(200), nullable=False),
        sa.Column("business_unit_id", sa.String(64), sa.ForeignKey("business_units.id")),
        sa.Column("raw_manifest_id", sa.String(64), sa.ForeignKey("raw_page_manifests.id"),
                  nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True)),
        sa.Column("fact_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(80), nullable=False),
        sa.Column("store_key", sa.String(160)),
        sa.Column("warehouse_key", sa.String(160)),
        sa.Column("product_key", sa.String(160)),
        sa.Column("source_local_time", sa.String(64)),
        sa.Column("source_timezone", sa.String(64)),
        sa.Column("business_date", sa.Date()),
        sa.Column("amount", sa.Numeric(38, 12)),
        sa.Column("currency_code", sa.String(8)),
        sa.Column("quantity", sa.Numeric(38, 12)),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.UniqueConstraint("external_system_id", "resource_key", "external_key"),
    )
    for column in (
        "enterprise_id", "external_system_id", "resource_key", "business_unit_id",
        "raw_manifest_id", "fact_type", "status", "store_key", "warehouse_key",
        "product_key", "business_date",
    ):
        op.create_index(f"ix_canonical_operational_facts_{column}",
                        "canonical_operational_facts", [column])


def downgrade() -> None:
    op.drop_table("canonical_operational_facts")
