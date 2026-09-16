"""Add source order totals and inventory balances without fabricating paid facts."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0058_canonical_source_facts"
down_revision = "0057_source_scope_and_manifest_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _provenance() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
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
    ]


def upgrade() -> None:
    # Forward repair for a SQLite database that replayed the earlier 0057 draft.
    if op.get_bind().dialect.name == "sqlite":
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints("raw_page_manifests"):
            if constraint["column_names"] == ["content_hash"]:
                with op.batch_alter_table(
                    "raw_page_manifests", recreate="always",
                    naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"},
                ) as batch:
                    batch.drop_constraint(
                        constraint["name"] or "uq_raw_page_manifests_content_hash", type_="unique"
                    )
    op.create_table(
        "canonical_entity_origins", *_provenance(),
        sa.Column("entity_id", sa.String(64), sa.ForeignKey("business_entities.id"),
                  nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.UniqueConstraint("external_system_id", "resource_key", "external_key"),
    )
    op.create_table(
        "canonical_sales_orders", *_provenance(),
        sa.Column("store_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(38, 12)), sa.Column("currency_code", sa.String(8)),
        sa.Column("base_amount", sa.Numeric(38, 12)),
        sa.Column("base_currency_code", sa.String(8)),
        sa.Column("exchange_rate_version", sa.String(64)),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_local_time", sa.String(64), nullable=False),
        sa.Column("store_timezone", sa.String(64)),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("fulfillment_channel", sa.String(32)),
        sa.UniqueConstraint("external_system_id", "resource_key", "external_key"),
    )
    op.create_table(
        "canonical_sales_order_lines",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("order_id", sa.String(64), sa.ForeignKey("canonical_sales_orders.id"),
                  nullable=False),
        sa.Column("line_key", sa.String(64), nullable=False),
        sa.Column("sku", sa.String(160), nullable=False),
        sa.Column("local_sku", sa.String(160)),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("order_id", "line_key"),
    )
    op.create_table(
        "canonical_inventory_balances", *_provenance(),
        sa.Column("warehouse_key", sa.String(160), nullable=False),
        sa.Column("product_key", sa.String(160), nullable=False),
        sa.Column("sku", sa.String(160), nullable=False), sa.Column("store_key", sa.String(160)),
        *(sa.Column(name, sa.BigInteger(), nullable=False) for name in
          ("total", "available", "defective", "inspecting", "reserved")),
        sa.Column("in_transit", sa.BigInteger()),
        sa.UniqueConstraint("external_system_id", "resource_key", "external_key"),
    )
    op.create_table(
        "staging_page_results",
        sa.Column("raw_manifest_id", sa.String(64), sa.ForeignKey("raw_page_manifests.id"),
                  primary_key=True),
        *(sa.Column(name, sa.Integer(), nullable=False) for name in
          ("accepted", "rejected", "unassigned", "stale")),
        sa.Column("mapping_version", sa.String(32), nullable=False),
    )
    for table in ("canonical_entity_origins", "canonical_sales_orders",
                  "canonical_inventory_balances"):
        for column in ("enterprise_id", "external_system_id", "business_unit_id",
                       "raw_manifest_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index("ix_canonical_sales_order_lines_order_id", "canonical_sales_order_lines",
                    ["order_id"])
    if op.get_bind().dialect.name != "sqlite":
        op.create_unique_constraint("uq_raw_page_run_page", "raw_page_manifests",
                                    ["sync_resource_run_id", "page_number"])
    else:
        op.create_index("uq_raw_page_run_page", "raw_page_manifests",
                        ["sync_resource_run_id", "page_number"], unique=True)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.drop_index("uq_raw_page_run_page", table_name="raw_page_manifests")
    else:
        op.drop_constraint("uq_raw_page_run_page", "raw_page_manifests", type_="unique")
    for table in ("staging_page_results", "canonical_inventory_balances",
                  "canonical_sales_order_lines", "canonical_sales_orders",
                  "canonical_entity_origins"):
        op.drop_table(table)
