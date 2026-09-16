"""Add resumable historical backfill plans and explicit coverage windows."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0072_source_backfill_coverage"
down_revision = "0071_source_binding_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_sync_schedules", sa.Column(
        "resource_version", sa.String(32), nullable=False, server_default="unknown"))
    op.execute(sa.text(
        "UPDATE source_sync_schedules SET resource_version = COALESCE((SELECT sr.version "
        "FROM source_resources sr WHERE sr.external_system_id = "
        "source_sync_schedules.external_system_id AND sr.resource_key = "
        "source_sync_schedules.resource_key), 'unknown')"))
    op.create_table(
        "source_backfill_plans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("external_system_id", sa.String(64), sa.ForeignKey("external_systems.id"),
                  nullable=False),
        sa.Column("source_resource_id", sa.String(64), sa.ForeignKey("source_resources.id"),
                  nullable=False),
        sa.Column("resource_version", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("resource_key", sa.String(120), nullable=False),
        sa.Column("resource_parameters", sa.JSON(), nullable=False,
                  server_default=sa.text("'{}'")),
        sa.Column("projection_mode", sa.String(20), nullable=False, server_default="deferred"),
        sa.Column("status", sa.String(32), nullable=False, server_default="paused"),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cursor", sa.DateTime(timezone=True), nullable=False),
        sa.Column("partition_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="16"),
        sa.Column("active_run_id", sa.String(64), sa.ForeignKey("sync_runs.id")),
        sa.Column("windows_total", sa.Integer(), nullable=False),
        sa.Column("windows_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("windows_no_data", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("windows_with_conflicts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("windows_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_read", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("records_written", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("scope_snapshot", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(120)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("window_start < window_end", name="ck_backfill_window_order"),
        sa.CheckConstraint("cursor >= window_start AND cursor <= window_end",
                           name="ck_backfill_cursor_range"),
        sa.CheckConstraint("partition_days BETWEEN 1 AND 7", name="ck_backfill_partition_days"),
        sa.CheckConstraint("batch_size BETWEEN 1 AND 32", name="ck_backfill_batch_size"),
        sa.CheckConstraint("status IN ('paused','active','needs_attention','completed')",
                           name="ck_backfill_status"),
        sa.CheckConstraint("windows_total >= 0 AND windows_succeeded >= 0 AND "
                           "windows_no_data >= 0 AND windows_with_conflicts >= 0 AND "
                           "windows_failed >= 0 AND records_read >= 0 AND records_written >= 0",
                           name="ck_backfill_nonnegative_counts"),
        sa.CheckConstraint("version >= 1", name="ck_backfill_version"),
    )
    for column in ("enterprise_id", "external_system_id", "source_resource_id", "status"):
        op.create_index(f"ix_source_backfill_plans_{column}", "source_backfill_plans", [column])
    op.create_index("ix_source_backfill_dispatch", "source_backfill_plans",
                    ["status", "active_run_id", "updated_at"])
    op.create_table(
        "source_coverage_windows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("backfill_plan_id", sa.String(64),
                  sa.ForeignKey("source_backfill_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_system_id", sa.String(64), sa.ForeignKey("external_systems.id"),
                  nullable=False),
        sa.Column("source_resource_id", sa.String(64), sa.ForeignKey("source_resources.id"),
                  nullable=False),
        sa.Column("resource_version", sa.String(32), nullable=False),
        sa.Column("resource_key", sa.String(120), nullable=False),
        sa.Column("partition_key", sa.String(64), nullable=False),
        sa.Column("resource_parameters", sa.JSON(), nullable=False,
                  server_default=sa.text("'{}'")),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sync_run_id", sa.String(64), sa.ForeignKey("sync_runs.id")),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("records_read", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("records_written", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(120)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("backfill_plan_id", "window_start", "window_end",
                            name="uq_source_coverage_windows_plan_range"),
        sa.CheckConstraint("window_start < window_end", name="ck_coverage_window_order"),
        sa.CheckConstraint("status IN ('queued','running','succeeded','no_data',"
                           "'succeeded_with_conflicts','failed','cancelled')",
                           name="ck_coverage_status"),
        sa.CheckConstraint("records_read >= 0 AND records_written >= 0 AND attempt_count >= 0",
                           name="ck_coverage_nonnegative_counts"),
    )
    for column in ("enterprise_id", "backfill_plan_id", "external_system_id",
                   "source_resource_id", "partition_key", "window_start", "status"):
        op.create_index(f"ix_source_coverage_windows_{column}", "source_coverage_windows", [column])


def downgrade() -> None:
    op.drop_table("source_coverage_windows")
    op.drop_table("source_backfill_plans")
    op.drop_column("source_sync_schedules", "resource_version")
