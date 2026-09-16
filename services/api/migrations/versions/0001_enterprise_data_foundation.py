"""Create the enterprise data integration foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_data_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "enterprises",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_enterprises_code", "enterprises", ["code"])
    op.create_table(
        "external_systems",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("system_key", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("system_type", sa.String(80), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("source_schema_version", sa.String(32), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("enterprise_id", "system_key"),
    )
    op.create_index("ix_external_systems_enterprise_id", "external_systems", ["enterprise_id"])
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "external_system_id",
            sa.String(64),
            sa.ForeignKey("external_systems.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("scenario", sa.String(32), nullable=False),
        sa.Column("records_read", sa.Integer(), nullable=False),
        sa.Column("records_written", sa.Integer(), nullable=False),
        sa.Column("warning", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sync_runs_enterprise_id", "sync_runs", ["enterprise_id"])
    op.create_index("ix_sync_runs_external_system_id", "sync_runs", ["external_system_id"])
    op.create_index("ix_sync_runs_status", "sync_runs", ["status"])
    op.create_table(
        "source_records",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "external_system_id",
            sa.String(64),
            sa.ForeignKey("external_systems.id"),
            nullable=False,
        ),
        sa.Column("sync_run_id", sa.String(64), sa.ForeignKey("sync_runs.id"), nullable=False),
        sa.Column("record_type", sa.String(80), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("source_schema_version", sa.String(32), nullable=False),
        sa.Column("mapping_version", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("external_system_id", "record_type", "external_id", "content_hash"),
    )
    op.create_index("ix_source_records_enterprise_id", "source_records", ["enterprise_id"])
    op.create_index(
        "ix_source_records_external_system_id", "source_records", ["external_system_id"]
    )
    op.create_index("ix_source_records_sync_run_id", "source_records", ["sync_run_id"])
    op.create_table(
        "business_entities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("canonical_key", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enterprise_id", "entity_type", "canonical_key"),
    )
    op.create_index("ix_business_entities_enterprise_id", "business_entities", ["enterprise_id"])
    op.create_table(
        "metric_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "source_system_id", sa.String(64), sa.ForeignKey("external_systems.id"), nullable=True
        ),
        sa.Column("sync_run_id", sa.String(64), sa.ForeignKey("sync_runs.id"), nullable=True),
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("change_rate", sa.Float(), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_metric_snapshots_enterprise_id", "metric_snapshots", ["enterprise_id"])
    op.create_index(
        "ix_metric_snapshots_source_system_id", "metric_snapshots", ["source_system_id"]
    )
    op.create_index("ix_metric_snapshots_sync_run_id", "metric_snapshots", ["sync_run_id"])
    op.create_index("ix_metric_snapshots_metric_key", "metric_snapshots", ["metric_key"])
    op.create_index("ix_metric_snapshots_as_of", "metric_snapshots", ["as_of"])
    op.create_table(
        "twin_nodes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("node_key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("node_type", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("health", sa.Float(), nullable=False),
        sa.Column("position_x", sa.Float(), nullable=False),
        sa.Column("position_y", sa.Float(), nullable=False),
        sa.Column("position_z", sa.Float(), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.UniqueConstraint("enterprise_id", "node_key"),
    )
    op.create_index("ix_twin_nodes_enterprise_id", "twin_nodes", ["enterprise_id"])
    op.create_table(
        "twin_edges",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("edge_key", sa.String(120), nullable=False),
        sa.Column("source_key", sa.String(100), nullable=False),
        sa.Column("target_key", sa.String(100), nullable=False),
        sa.Column("flow_type", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("traffic", sa.Float(), nullable=False),
        sa.UniqueConstraint("enterprise_id", "edge_key"),
    )
    op.create_index("ix_twin_edges_enterprise_id", "twin_edges", ["enterprise_id"])
    op.create_table(
        "platform_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("detail", sa.String(500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_platform_events_enterprise_id", "platform_events", ["enterprise_id"])
    op.create_index("ix_platform_events_occurred_at", "platform_events", ["occurred_at"])


def downgrade() -> None:
    for table in [
        "platform_events",
        "twin_edges",
        "twin_nodes",
        "metric_snapshots",
        "business_entities",
        "source_records",
        "sync_runs",
        "external_systems",
        "enterprises",
    ]:
        op.drop_table(table)
