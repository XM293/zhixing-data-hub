"""Add governed, scoped, and idempotent digital meeting creation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_scoped_meeting_creation"
down_revision: str | None = "0026_ai_provider_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("twin_meetings") as batch_op:
        batch_op.add_column(
            sa.Column("initiated_by_principal_id", sa.String(64), nullable=True)
        )
        batch_op.add_column(sa.Column("actor_snapshot", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("idempotency_key", sa.String(160), nullable=True))
        batch_op.add_column(sa.Column("request_hash", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "scope_type",
                sa.String(32),
                nullable=False,
                server_default="enterprise",
            )
        )
        batch_op.add_column(
            sa.Column(
                "scope_key",
                sa.String(160),
                nullable=False,
                server_default="enterprise",
            )
        )
        batch_op.create_foreign_key(
            "fk_twin_meetings_initiated_by_principal_id",
            "principals",
            ["initiated_by_principal_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_twin_meetings_enterprise_idempotency_key",
            ["enterprise_id", "idempotency_key"],
        )
        for column in (
            "initiated_by_principal_id",
            "idempotency_key",
            "scope_type",
            "scope_key",
        ):
            batch_op.create_index(f"ix_twin_meetings_{column}", [column])


def downgrade() -> None:
    with op.batch_alter_table("twin_meetings") as batch_op:
        for column in (
            "scope_key",
            "scope_type",
            "idempotency_key",
            "initiated_by_principal_id",
        ):
            batch_op.drop_index(f"ix_twin_meetings_{column}")
        batch_op.drop_constraint(
            "uq_twin_meetings_enterprise_idempotency_key",
            type_="unique",
        )
        batch_op.drop_constraint(
            "fk_twin_meetings_initiated_by_principal_id",
            type_="foreignkey",
        )
        batch_op.drop_column("scope_key")
        batch_op.drop_column("scope_type")
        batch_op.drop_column("request_hash")
        batch_op.drop_column("idempotency_key")
        batch_op.drop_column("actor_snapshot")
        batch_op.drop_column("initiated_by_principal_id")
