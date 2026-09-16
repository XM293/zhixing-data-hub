"""Add governed organization, position and access-role catalog operations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0038_identity_catalog_operations"
down_revision: str | None = "0037_identity_management_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("org_units") as batch_op:
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )
    with op.batch_alter_table("positions") as batch_op:
        batch_op.add_column(
            sa.Column("version", sa.Integer(), nullable=False, server_default="1")
        )
    with op.batch_alter_table("access_roles") as batch_op:
        batch_op.add_column(
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
        )

    op.create_table(
        "identity_catalog_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(96), nullable=False),
        sa.Column("target_type", sa.String(48), nullable=False),
        sa.Column("target_key", sa.String(160), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("before_snapshot", sa.JSON(), nullable=False),
        sa.Column("after_snapshot", sa.JSON(), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    for column in (
        "enterprise_id",
        "event_type",
        "target_type",
        "target_key",
        "actor_principal_id",
        "idempotency_key",
        "request_id",
        "run_id",
        "occurred_at",
    ):
        op.create_index(
            f"ix_identity_catalog_events_{column}",
            "identity_catalog_events",
            [column],
        )


def downgrade() -> None:
    op.drop_table("identity_catalog_events")
    with op.batch_alter_table("access_roles") as batch_op:
        batch_op.drop_column("revision")
    with op.batch_alter_table("positions") as batch_op:
        batch_op.drop_column("version")
    with op.batch_alter_table("org_units") as batch_op:
        batch_op.drop_column("version")
