"""Add platform operations, configuration, notification, file, exchange and delegation controls."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_platform_management_controls"
down_revision: str | None = "0043_channel_identity_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enterprise_table(name: str, *columns: sa.Column[object], constraints: object = None) -> None:
    args: list[object] = [
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        *columns,
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
    ]
    if constraints:
        args.extend(constraints if isinstance(constraints, list) else [constraints])
    op.create_table(name, *args)
    op.create_index(f"ix_{name}_enterprise", name, ["enterprise_id"])


def upgrade() -> None:
    _enterprise_table(
        "platform_operation_events",
        sa.Column("event_type", sa.String(96), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("target_id", sa.String(160), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
        constraints=sa.UniqueConstraint("enterprise_id", "idempotency_key", name="uq_platform_operation_event_request"),
    )
    for column in ("event_type", "target_type", "target_id", "actor_principal_id", "request_id", "run_id", "occurred_at"):
        op.create_index(f"ix_platform_operation_events_{column}", "platform_operation_events", [column])

    _enterprise_table(
        "platform_parameters",
        sa.Column("parameter_key", sa.String(160), nullable=False),
        sa.Column("group_key", sa.String(80), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("value_type", sa.String(32), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by_principal_id", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_principal_id"], ["principals.id"]),
        constraints=sa.UniqueConstraint("enterprise_id", "parameter_key", name="uq_platform_parameter_key"),
    )
    op.create_index("ix_platform_parameters_group", "platform_parameters", ["group_key"])
    op.create_index("ix_platform_parameters_status", "platform_parameters", ["status"])

    _enterprise_table(
        "platform_dictionary_types",
        sa.Column("dictionary_key", sa.String(120), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        constraints=sa.UniqueConstraint("enterprise_id", "dictionary_key", name="uq_platform_dictionary_key"),
    )
    op.create_index("ix_platform_dictionary_types_status", "platform_dictionary_types", ["status"])
    _enterprise_table(
        "platform_dictionary_items",
        sa.Column("dictionary_type_id", sa.String(64), nullable=False),
        sa.Column("item_key", sa.String(120), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["dictionary_type_id"], ["platform_dictionary_types.id"], ondelete="CASCADE"),
        constraints=sa.UniqueConstraint("dictionary_type_id", "item_key", name="uq_platform_dictionary_item_key"),
    )
    op.create_index("ix_platform_dictionary_items_type", "platform_dictionary_items", ["dictionary_type_id"])
    op.create_index("ix_platform_dictionary_items_status", "platform_dictionary_items", ["status"])

    _enterprise_table(
        "domain_events",
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("aggregate_type", sa.String(80), nullable=False),
        sa.Column("aggregate_id", sa.String(160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        constraints=sa.UniqueConstraint("enterprise_id", "event_key", name="uq_domain_event_key"),
    )
    for column in ("event_type", "aggregate_type", "aggregate_id", "status", "occurred_at"):
        op.create_index(f"ix_domain_events_{column}", "domain_events", [column])

    _enterprise_table(
        "notifications",
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("source_event_id", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("body", sa.String(1000), nullable=False),
        sa.Column("severity", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("action_route", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["source_event_id"], ["domain_events.id"]),
    )
    for column in ("principal_id", "source_event_id", "category", "severity", "status", "created_at"):
        op.create_index(f"ix_notifications_{column}", "notifications", [column])
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("notification_id", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("notification_id", "channel", name="uq_notification_delivery_channel"),
    )
    op.create_index("ix_notification_deliveries_notification", "notification_deliveries", ["notification_id"])
    op.create_index("ix_notification_deliveries_status", "notification_deliveries", ["status"])

    _enterprise_table(
        "file_assets",
        sa.Column("asset_key", sa.String(160), nullable=False),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("media_type", sa.String(160), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("storage_provider", sa.String(48), nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False, unique=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("uploaded_by_principal_id", sa.String(64), nullable=False),
        sa.Column("required_permission", sa.String(120), nullable=False),
        sa.Column("scope_type", sa.String(48), nullable=False),
        sa.Column("scope_id", sa.String(160), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uploaded_by_principal_id"], ["principals.id"]),
        constraints=sa.UniqueConstraint("enterprise_id", "asset_key", name="uq_file_asset_key"),
    )
    for column in ("checksum_sha256", "category", "status", "created_at"):
        op.create_index(f"ix_file_assets_{column}", "file_assets", [column])

    _enterprise_table(
        "bulk_exchange_jobs",
        sa.Column("operation", sa.String(24), nullable=False),
        sa.Column("dataset_key", sa.String(120), nullable=False),
        sa.Column("file_format", sa.String(24), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("file_asset_id", sa.String(64), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invalid_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applied_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_summary", sa.JSON(), nullable=False),
        sa.Column("requested_by_principal_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["file_asset_id"], ["file_assets.id"]),
        sa.ForeignKeyConstraint(["requested_by_principal_id"], ["principals.id"]),
        constraints=sa.UniqueConstraint("enterprise_id", "idempotency_key", name="uq_bulk_exchange_request"),
    )
    for column in ("operation", "dataset_key", "status", "file_asset_id", "created_at"):
        op.create_index(f"ix_bulk_exchange_jobs_{column}", "bulk_exchange_jobs", [column])
    op.create_table(
        "bulk_exchange_rows",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("exchange_job_id", sa.String(64), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_data", sa.JSON(), nullable=False),
        sa.Column("normalized_data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["exchange_job_id"], ["bulk_exchange_jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("exchange_job_id", "row_number", name="uq_bulk_exchange_row_number"),
    )
    op.create_index("ix_bulk_exchange_rows_job", "bulk_exchange_rows", ["exchange_job_id"])
    op.create_index("ix_bulk_exchange_rows_status", "bulk_exchange_rows", ["status"])

    _enterprise_table(
        "access_delegations",
        sa.Column("delegation_key", sa.String(160), nullable=False),
        sa.Column("delegator_principal_id", sa.String(64), nullable=False),
        sa.Column("delegatee_principal_id", sa.String(64), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_principal_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["delegator_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["delegatee_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        constraints=sa.UniqueConstraint("enterprise_id", "delegation_key", name="uq_access_delegation_key"),
    )
    for column in ("delegator_principal_id", "delegatee_principal_id", "status", "valid_from", "valid_to"):
        op.create_index(f"ix_access_delegations_{column}", "access_delegations", [column])


def downgrade() -> None:
    for table in (
        "access_delegations",
        "bulk_exchange_rows",
        "bulk_exchange_jobs",
        "file_assets",
        "notification_deliveries",
        "notifications",
        "domain_events",
        "platform_dictionary_items",
        "platform_dictionary_types",
        "platform_parameters",
        "platform_operation_events",
    ):
        op.drop_table(table)
