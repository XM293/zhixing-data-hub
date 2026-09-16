"""Add governed external channel identity bindings and lifecycle events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_channel_identity_bindings"
down_revision: str | None = "0042_trusted_mcp_gateway_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_identities",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("channel_key", sa.String(48), nullable=False),
        sa.Column("external_tenant_key", sa.String(160), nullable=False),
        sa.Column("external_identity_hash", sa.String(64), nullable=False),
        sa.Column("external_identity_hint", sa.String(32), nullable=False),
        sa.Column("observed_display_name", sa.String(160), nullable=True),
        sa.Column("principal_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["principal_id"], ["principals.id"]),
        sa.UniqueConstraint(
            "enterprise_id",
            "channel_key",
            "external_tenant_key",
            "external_identity_hash",
            name="uq_channel_identity_external_key",
        ),
    )
    op.create_index("ix_channel_identities_enterprise", "channel_identities", ["enterprise_id"])
    op.create_index("ix_channel_identities_principal", "channel_identities", ["principal_id"])
    op.create_index("ix_channel_identities_status", "channel_identities", ["status"])
    op.create_index("ix_channel_identities_last_seen", "channel_identities", ["last_seen_at"])

    op.create_table(
        "channel_identity_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("channel_identity_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("before_principal_id", sa.String(64), nullable=True),
        sa.Column("after_principal_id", sa.String(64), nullable=True),
        sa.Column("before_status", sa.String(32), nullable=False),
        sa.Column("after_status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["channel_identity_id"], ["channel_identities.id"]),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["before_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["after_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "idempotency_key", name="uq_channel_identity_event_request"),
    )
    op.create_index("ix_channel_identity_events_enterprise", "channel_identity_events", ["enterprise_id"])
    op.create_index("ix_channel_identity_events_identity", "channel_identity_events", ["channel_identity_id"])
    op.create_index("ix_channel_identity_events_actor", "channel_identity_events", ["actor_principal_id"])
    op.create_index("ix_channel_identity_events_type", "channel_identity_events", ["event_type"])
    op.create_index("ix_channel_identity_events_request", "channel_identity_events", ["request_id"])
    op.create_index("ix_channel_identity_events_run", "channel_identity_events", ["run_id"])
    op.create_index("ix_channel_identity_events_occurred", "channel_identity_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_channel_identity_events_occurred", table_name="channel_identity_events")
    op.drop_index("ix_channel_identity_events_run", table_name="channel_identity_events")
    op.drop_index("ix_channel_identity_events_request", table_name="channel_identity_events")
    op.drop_index("ix_channel_identity_events_type", table_name="channel_identity_events")
    op.drop_index("ix_channel_identity_events_actor", table_name="channel_identity_events")
    op.drop_index("ix_channel_identity_events_identity", table_name="channel_identity_events")
    op.drop_index("ix_channel_identity_events_enterprise", table_name="channel_identity_events")
    op.drop_table("channel_identity_events")
    op.drop_index("ix_channel_identities_last_seen", table_name="channel_identities")
    op.drop_index("ix_channel_identities_status", table_name="channel_identities")
    op.drop_index("ix_channel_identities_principal", table_name="channel_identities")
    op.drop_index("ix_channel_identities_enterprise", table_name="channel_identities")
    op.drop_table("channel_identities")
