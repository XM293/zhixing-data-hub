"""Add evidence-grounded customer service conversations and reply workflow."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_customer_service_copilot"
down_revision: str | None = "0024_business_analysis_and_briefs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_service_conversations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("conversation_key", sa.String(120), nullable=False),
        sa.Column("channel_key", sa.String(64), nullable=False),
        sa.Column("external_conversation_id", sa.String(160), nullable=True),
        sa.Column("source_system_key", sa.String(100), nullable=False),
        sa.Column("customer_key", sa.String(160), nullable=False),
        sa.Column("customer_name", sa.String(160), nullable=False),
        sa.Column("order_key", sa.String(160), nullable=True),
        sa.Column("store_scope_key", sa.String(160), nullable=False),
        sa.Column("topic", sa.String(240), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(24), nullable=False),
        sa.Column("sentiment", sa.String(24), nullable=False),
        sa.Column("risk_level", sa.String(24), nullable=False),
        sa.Column("risk_reason", sa.String(1000), nullable=False),
        sa.Column("assigned_principal_id", sa.String(64), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_response_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latest_sync_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["assigned_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "channel_key", "conversation_key"),
    )
    for column in (
        "enterprise_id", "conversation_key", "channel_key", "external_conversation_id",
        "source_system_key", "customer_key", "order_key", "store_scope_key", "status",
        "priority", "sentiment", "risk_level", "assigned_principal_id", "last_message_at",
        "first_response_due_at", "latest_sync_at", "updated_at",
    ):
        op.create_index(
            f"ix_customer_service_conversations_{column}",
            "customer_service_conversations",
            [column],
        )

    op.create_table(
        "customer_service_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("message_key", sa.String(120), nullable=False),
        sa.Column("sender_type", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("sender_name", sa.String(160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(32), nullable=False),
        sa.Column("source_message_id", sa.String(160), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["customer_service_conversations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("conversation_id", "message_key"),
    )
    for column in (
        "enterprise_id", "conversation_id", "sender_type", "direction",
        "delivery_status", "occurred_at",
    ):
        op.create_index(
            f"ix_customer_service_messages_{column}",
            "customer_service_messages",
            [column],
        )

    op.create_table(
        "customer_service_order_contexts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("context_type", sa.String(32), nullable=False),
        sa.Column("order_key", sa.String(160), nullable=True),
        sa.Column("order_status", sa.String(64), nullable=True),
        sa.Column("paid_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("product_summary", sa.String(500), nullable=False),
        sa.Column("item_quantity", sa.Integer(), nullable=False),
        sa.Column("payment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("logistics_status", sa.String(64), nullable=True),
        sa.Column("carrier", sa.String(120), nullable=True),
        sa.Column("tracking_no", sa.String(160), nullable=True),
        sa.Column("latest_logistics_event", sa.Text(), nullable=True),
        sa.Column("promised_delivery_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_logistics_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delayed_hours", sa.Integer(), nullable=False),
        sa.Column("aftersale_status", sa.String(64), nullable=True),
        sa.Column("source_system_key", sa.String(100), nullable=False),
        sa.Column("payload_version", sa.String(32), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["customer_service_conversations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("conversation_id"),
    )
    for column in (
        "enterprise_id", "conversation_id", "context_type", "order_key",
        "source_system_key", "synced_at",
    ):
        op.create_index(
            f"ix_customer_service_order_contexts_{column}",
            "customer_service_order_contexts",
            [column],
        )

    op.create_table(
        "customer_service_reply_drafts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(24), nullable=False),
        sa.Column("risk_flags", sa.JSON(), nullable=False),
        sa.Column("safe_to_send", sa.Boolean(), nullable=False),
        sa.Column("suggested_action", sa.String(32), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("execution_mode", sa.String(32), nullable=False),
        sa.Column("fallback_reason", sa.String(1000), nullable=True),
        sa.Column("evidence_snapshot_id", sa.String(64), nullable=False),
        sa.Column("agent_run_id", sa.String(64), nullable=False),
        sa.Column("role_twin_version_id", sa.String(64), nullable=False),
        sa.Column("created_by_principal_id", sa.String(64), nullable=False),
        sa.Column("approved_by_principal_id", sa.String(64), nullable=True),
        sa.Column("approval_note", sa.String(1000), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["customer_service_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["evidence_snapshot_id"], ["evidence_snapshots.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["role_twin_version_id"], ["role_twin_versions.id"]),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["approved_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("conversation_id", "version_number"),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    for column in (
        "enterprise_id", "conversation_id", "status", "risk_level", "safe_to_send",
        "execution_mode", "evidence_snapshot_id", "agent_run_id", "role_twin_version_id",
        "created_by_principal_id", "approved_by_principal_id", "idempotency_key",
        "request_id", "run_id", "created_at", "approved_at",
    ):
        op.create_index(
            f"ix_customer_service_reply_drafts_{column}",
            "customer_service_reply_drafts",
            [column],
        )

    op.create_table(
        "customer_service_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("conversation_id", sa.String(64), nullable=False),
        sa.Column("reply_draft_id", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["customer_service_conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["reply_draft_id"], ["customer_service_reply_drafts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    for column in (
        "enterprise_id", "conversation_id", "reply_draft_id", "event_type",
        "actor_principal_id", "idempotency_key", "request_id", "run_id", "occurred_at",
    ):
        op.create_index(
            f"ix_customer_service_events_{column}",
            "customer_service_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("customer_service_events")
    op.drop_table("customer_service_reply_drafts")
    op.drop_table("customer_service_order_contexts")
    op.drop_table("customer_service_messages")
    op.drop_table("customer_service_conversations")
