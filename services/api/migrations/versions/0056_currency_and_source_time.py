"""Preserve source currency and source-local timestamps alongside legacy facts."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0056_currency_and_source_time"
down_revision: str | None = "0055_lingxing_scope_and_run_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    additions: dict[str, list[sa.Column[object]]] = {
        "source_records": [
            sa.Column("source_timezone", sa.String(64), nullable=True),
            sa.Column("source_observed_at", sa.DateTime(timezone=True), nullable=True),
        ],
        "commerce_order_facts": [
            sa.Column("currency_code", sa.String(8), nullable=True),
            sa.Column("original_paid_amount", sa.Float(), nullable=True),
            sa.Column("base_currency_code", sa.String(8), nullable=True),
            sa.Column("base_paid_amount", sa.Float(), nullable=True),
            sa.Column("exchange_rate_version", sa.String(64), nullable=True),
        ],
        "commerce_order_line_facts": [
            sa.Column("currency_code", sa.String(8), nullable=True),
            sa.Column("original_refund_amount", sa.Float(), nullable=True),
            sa.Column("base_currency_code", sa.String(8), nullable=True),
            sa.Column("base_refund_amount", sa.Float(), nullable=True),
            sa.Column("exchange_rate_version", sa.String(64), nullable=True),
        ],
        "commerce_refund_facts": [
            sa.Column("currency_code", sa.String(8), nullable=True),
            sa.Column("original_refund_amount", sa.Float(), nullable=True),
            sa.Column("base_currency_code", sa.String(8), nullable=True),
            sa.Column("base_refund_amount", sa.Float(), nullable=True),
            sa.Column("exchange_rate_version", sa.String(64), nullable=True),
        ],
        "commerce_inventory_snapshot_facts": [
            sa.Column("currency_code", sa.String(8), nullable=True),
            sa.Column("original_inventory_cost", sa.Float(), nullable=True),
            sa.Column("base_currency_code", sa.String(8), nullable=True),
            sa.Column("base_inventory_cost", sa.Float(), nullable=True),
            sa.Column("exchange_rate_version", sa.String(64), nullable=True),
        ],
        "commerce_ad_performance_facts": [
            sa.Column("currency_code", sa.String(8), nullable=True),
            sa.Column("original_spend", sa.Float(), nullable=True),
            sa.Column("base_currency_code", sa.String(8), nullable=True),
            sa.Column("base_spend", sa.Float(), nullable=True),
            sa.Column("exchange_rate_version", sa.String(64), nullable=True),
        ],
    }
    inspector = sa.inspect(op.get_bind())
    for table, columns in additions.items():
        existing = {item["name"] for item in inspector.get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)


def downgrade() -> None:
    removals = {
        "commerce_ad_performance_facts": [
            "exchange_rate_version", "base_spend", "base_currency_code",
            "original_spend", "currency_code",
        ],
        "commerce_inventory_snapshot_facts": [
            "exchange_rate_version", "base_inventory_cost", "base_currency_code",
            "original_inventory_cost", "currency_code",
        ],
        "commerce_refund_facts": [
            "exchange_rate_version", "base_refund_amount", "base_currency_code",
            "original_refund_amount", "currency_code",
        ],
        "commerce_order_facts": [
            "exchange_rate_version", "base_paid_amount", "base_currency_code",
            "original_paid_amount", "currency_code",
        ],
        "commerce_order_line_facts": [
            "exchange_rate_version", "base_refund_amount", "base_currency_code",
            "original_refund_amount", "currency_code",
        ],
        "source_records": ["source_observed_at", "source_timezone"],
    }
    inspector = sa.inspect(op.get_bind())
    for table, columns in removals.items():
        existing = {item["name"] for item in inspector.get_columns(table)}
        for column in columns:
            if column in existing:
                op.drop_column(table, column)
