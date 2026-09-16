"""Add canonical commerce fact tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_canonical_commerce_facts"
down_revision: str | None = "0029_knowledge_provider_evaluations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _common_fact_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "external_system_id",
            sa.String(64),
            sa.ForeignKey("external_systems.id"),
            nullable=False,
        ),
        sa.Column("sync_run_id", sa.String(64), sa.ForeignKey("sync_runs.id"), nullable=False),
    ]


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])


def upgrade() -> None:
    op.create_table(
        "commerce_order_facts",
        *_common_fact_columns(),
        sa.Column("order_key", sa.String(160), nullable=False),
        sa.Column("store_key", sa.String(160), nullable=False),
        sa.Column("customer_key", sa.String(160), nullable=False),
        sa.Column("channel", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("item_amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("discount_amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("freight_amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("cost_amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("province", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enterprise_id", "order_key", name="uq_commerce_order_fact_key"),
    )
    _indexes(
        "commerce_order_facts",
        "enterprise_id",
        "external_system_id",
        "sync_run_id",
        "order_key",
        "store_key",
        "customer_key",
        "status",
        "business_date",
    )

    op.create_table(
        "commerce_order_line_facts",
        *_common_fact_columns(),
        sa.Column(
            "order_id",
            sa.String(64),
            sa.ForeignKey("commerce_order_facts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("line_key", sa.String(160), nullable=False),
        sa.Column("order_key", sa.String(160), nullable=False),
        sa.Column("product_key", sa.String(160), nullable=False),
        sa.Column("sku_key", sa.String(160), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_fen", sa.BigInteger(), nullable=False),
        sa.Column("paid_amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("cost_amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("refund_quantity", sa.Integer(), nullable=False),
        sa.Column("refund_amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enterprise_id", "line_key", name="uq_commerce_order_line_fact_key"),
    )
    _indexes(
        "commerce_order_line_facts",
        "enterprise_id",
        "external_system_id",
        "sync_run_id",
        "order_id",
        "line_key",
        "order_key",
        "product_key",
        "sku_key",
    )

    op.create_table(
        "commerce_refund_facts",
        *_common_fact_columns(),
        sa.Column("refund_key", sa.String(160), nullable=False),
        sa.Column("order_key", sa.String(160), nullable=False),
        sa.Column("line_key", sa.String(160), nullable=False),
        sa.Column("store_key", sa.String(160), nullable=False),
        sa.Column("customer_key", sa.String(160), nullable=False),
        sa.Column("sku_key", sa.String(160), nullable=False),
        sa.Column("reason_category", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refund_amount_fen", sa.BigInteger(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enterprise_id", "refund_key", name="uq_commerce_refund_fact_key"),
    )
    _indexes(
        "commerce_refund_facts",
        "enterprise_id",
        "external_system_id",
        "sync_run_id",
        "refund_key",
        "order_key",
        "store_key",
        "sku_key",
        "status",
        "requested_at",
    )

    op.create_table(
        "commerce_inventory_snapshot_facts",
        *_common_fact_columns(),
        sa.Column("snapshot_key", sa.String(160), nullable=False),
        sa.Column("warehouse_key", sa.String(160), nullable=False),
        sa.Column("product_key", sa.String(160), nullable=False),
        sa.Column("sku_key", sa.String(160), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("in_transit_quantity", sa.Integer(), nullable=False),
        sa.Column("safety_quantity", sa.Integer(), nullable=False),
        sa.Column("inventory_cost_fen", sa.BigInteger(), nullable=False),
        sa.Column("days_cover", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "enterprise_id",
            "snapshot_key",
            name="uq_commerce_inventory_snapshot_fact_key",
        ),
    )
    _indexes(
        "commerce_inventory_snapshot_facts",
        "enterprise_id",
        "external_system_id",
        "sync_run_id",
        "snapshot_key",
        "warehouse_key",
        "product_key",
        "sku_key",
        "as_of",
        "status",
    )

    op.create_table(
        "commerce_ad_performance_facts",
        *_common_fact_columns(),
        sa.Column("performance_key", sa.String(160), nullable=False),
        sa.Column("campaign_key", sa.String(160), nullable=False),
        sa.Column("store_key", sa.String(160), nullable=False),
        sa.Column("product_key", sa.String(160), nullable=False),
        sa.Column("channel", sa.String(80), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.BigInteger(), nullable=False),
        sa.Column("clicks", sa.BigInteger(), nullable=False),
        sa.Column("spend_fen", sa.BigInteger(), nullable=False),
        sa.Column("attributed_order_count", sa.Integer(), nullable=False),
        sa.Column("attributed_revenue_fen", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "enterprise_id",
            "performance_key",
            name="uq_commerce_ad_performance_fact_key",
        ),
    )
    _indexes(
        "commerce_ad_performance_facts",
        "enterprise_id",
        "external_system_id",
        "sync_run_id",
        "performance_key",
        "campaign_key",
        "store_key",
        "product_key",
        "business_date",
    )


def downgrade() -> None:
    op.drop_table("commerce_ad_performance_facts")
    op.drop_table("commerce_inventory_snapshot_facts")
    op.drop_table("commerce_refund_facts")
    op.drop_table("commerce_order_line_facts")
    op.drop_table("commerce_order_facts")
