"""Add the metric catalog and versioned data quality results."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_data_catalog_quality"
down_revision: str | None = "0007_background_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "metric_definitions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("source_system_id", sa.String(64), nullable=True),
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("formula_expression", sa.String(1000), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("dimensions", sa.JSON(), nullable=False),
        sa.Column("owner", sa.String(160), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["source_system_id"], ["external_systems.id"]),
        sa.UniqueConstraint(
            "enterprise_id",
            "metric_key",
            "version",
            name="uq_metric_definitions_version",
        ),
    )
    op.create_index("ix_metric_definitions_enterprise_id", "metric_definitions", ["enterprise_id"])
    op.create_index("ix_metric_definitions_metric_key", "metric_definitions", ["metric_key"])
    op.create_index("ix_metric_definitions_status", "metric_definitions", ["status"])

    op.create_table(
        "data_quality_rules",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("rule_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("asset_type", sa.String(48), nullable=False),
        sa.Column("asset_key", sa.String(160), nullable=False),
        sa.Column("expectation", sa.String(500), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint("enterprise_id", "rule_key", name="uq_data_quality_rules_key"),
    )
    op.create_index("ix_data_quality_rules_enterprise_id", "data_quality_rules", ["enterprise_id"])
    op.create_index("ix_data_quality_rules_category", "data_quality_rules", ["category"])
    op.create_index("ix_data_quality_rules_status", "data_quality_rules", ["status"])

    op.create_table(
        "data_quality_results",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("sync_run_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("observed_value", sa.String(300), nullable=False),
        sa.Column("affected_records", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["rule_id"], ["data_quality_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_data_quality_results_enterprise_id", "data_quality_results", ["enterprise_id"]
    )
    op.create_index("ix_data_quality_results_rule_id", "data_quality_results", ["rule_id"])
    op.create_index("ix_data_quality_results_sync_run_id", "data_quality_results", ["sync_run_id"])
    op.create_index("ix_data_quality_results_status", "data_quality_results", ["status"])
    op.create_index("ix_data_quality_results_checked_at", "data_quality_results", ["checked_at"])


def downgrade() -> None:
    op.drop_table("data_quality_results")
    op.drop_table("data_quality_rules")
    op.drop_table("metric_definitions")
