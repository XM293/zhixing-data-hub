"""Add scope snapshots, run orchestration metadata, and raw lineage fields."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0055_lingxing_scope_and_run_metadata"
down_revision: str | None = "0054_lingxing_ingestion_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_columns(table: str, columns: list[sa.Column[object]]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {item["name"] for item in inspector.get_columns(table)}
    for column in columns:
        if column.name not in existing:
            op.add_column(table, column)


def upgrade() -> None:
    _add_columns(
        "external_systems",
        [
            sa.Column("credential_ref", sa.String(200), nullable=True),
            sa.Column("capability_version", sa.String(64), nullable=True),
            sa.Column("connection_status", sa.String(32), server_default="unknown"),
            sa.Column("last_probe_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        ],
    )
    _add_columns(
        "source_resources",
        [
            sa.Column("display_name", sa.String(160), nullable=True),
            sa.Column("version", sa.String(32), server_default="1"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        ],
    )
    _add_columns(
        "sync_resource_runs",
        [
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        ],
    )
    _add_columns(
        "sync_checkpoints",
        [sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True)],
    )
    _add_columns(
        "raw_page_manifests",
        [
            sa.Column("page_number", sa.Integer(), nullable=True),
            sa.Column("cursor", sa.String(300), nullable=True),
            sa.Column("schema_status", sa.String(32), server_default="unknown"),
            sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        ],
    )
    _add_columns(
        "mapping_conflicts",
        [
            # Added without an inline constraint so SQLite can replay 0053->head;
            # the ORM and PostgreSQL schema keep the relationship declarative.
            sa.Column("enterprise_id", sa.String(64), nullable=True),
            sa.Column("resource_key", sa.String(120), nullable=True),
            sa.Column("raw_manifest_id", sa.String(64), nullable=True),
            sa.Column("resolution", sa.JSON(), nullable=True),
        ],
    )
    _add_columns(
        "source_authority_rules",
        [
            sa.Column("group_id", sa.String(64), nullable=True),
            sa.Column("version", sa.String(32), server_default="1"),
            sa.Column("status", sa.String(32), server_default="active"),
        ],
    )
    _add_columns(
        "sync_runs",
        [
            sa.Column("parent_run_id", sa.String(64), nullable=True),
            sa.Column("request_id", sa.String(96), nullable=True),
            sa.Column("task_id", sa.String(96), nullable=True),
            sa.Column("idempotency_key", sa.String(160), nullable=True),
            sa.Column("trace_id", sa.String(96), nullable=True),
            sa.Column("scope_snapshot", sa.JSON(), nullable=True),
            sa.Column("selected_enterprise_ids", sa.JSON(), nullable=True),
            sa.Column("business_unit_ids", sa.JSON(), nullable=True),
            sa.Column("store_ids", sa.JSON(), nullable=True),
            sa.Column("warehouse_ids", sa.JSON(), nullable=True),
            sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("lease_owner", sa.String(120), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("retry_count", sa.Integer(), server_default="0"),
        ],
    )
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_mapping_conflicts_enterprise_id",
            "mapping_conflicts",
            "enterprises",
            ["enterprise_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_source_authority_rules_group_id",
            "source_authority_rules",
            "enterprise_groups",
            ["group_id"],
            ["id"],
        )
        op.create_foreign_key(
            "fk_sync_runs_parent_run_id",
            "sync_runs",
            "sync_runs",
            ["parent_run_id"],
            ["id"],
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        for name, table in (
            ("fk_sync_runs_parent_run_id", "sync_runs"),
            ("fk_source_authority_rules_group_id", "source_authority_rules"),
            ("fk_mapping_conflicts_enterprise_id", "mapping_conflicts"),
        ):
            op.drop_constraint(name, table_name=table, type_="foreignkey")
    removals = {
        "sync_runs": [
            "retry_count", "lease_expires_at", "lease_owner", "cancel_requested_at",
            "warehouse_ids", "store_ids", "business_unit_ids", "selected_enterprise_ids",
            "scope_snapshot", "trace_id", "idempotency_key", "task_id", "request_id",
            "parent_run_id",
        ],
        "source_authority_rules": ["status", "version", "group_id"],
        "mapping_conflicts": ["resolution", "raw_manifest_id", "resource_key", "enterprise_id"],
        "raw_page_manifests": ["fetched_at", "schema_status", "cursor", "page_number"],
        "sync_checkpoints": ["updated_at"],
        "sync_resource_runs": ["finished_at", "started_at"],
        "source_resources": ["updated_at", "version", "display_name"],
        "external_systems": [
            "updated_at", "disabled_at", "last_probe_at", "connection_status",
            "capability_version", "credential_ref",
        ],
    }
    inspector = sa.inspect(op.get_bind())
    for table, columns in removals.items():
        existing = {item["name"] for item in inspector.get_columns(table)}
        for column in columns:
            if column in existing:
                op.drop_column(table, column)
