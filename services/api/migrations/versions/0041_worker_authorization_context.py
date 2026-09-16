"""Add governed actor and execution context to background jobs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_worker_authorization_context"
down_revision: str | None = "0040_local_password_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("background_jobs") as batch_op:
        batch_op.add_column(sa.Column("actor_snapshot", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("permission_set_version", sa.String(96), nullable=True))
        batch_op.add_column(sa.Column("required_permissions", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("scope_type", sa.String(48), nullable=True))
        batch_op.add_column(sa.Column("scope_id", sa.String(160), nullable=True))
        batch_op.add_column(sa.Column("execution_token_hash", sa.String(64), nullable=True))

    jobs = sa.table(
        "background_jobs",
        sa.column("enterprise_id", sa.String),
        sa.column("actor_snapshot", sa.JSON),
        sa.column("permission_set_version", sa.String),
        sa.column("required_permissions", sa.JSON),
        sa.column("scope_type", sa.String),
        sa.column("scope_id", sa.String),
    )
    connection = op.get_bind()
    connection.execute(
        sa.update(jobs).values(
            actor_snapshot={"legacy_job": True},
            permission_set_version="legacy-unversioned",
            required_permissions=[],
            scope_type="enterprise",
            scope_id=jobs.c.enterprise_id,
        )
    )

    with op.batch_alter_table("background_jobs") as batch_op:
        batch_op.alter_column("actor_snapshot", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column(
            "permission_set_version", existing_type=sa.String(96), nullable=False
        )
        batch_op.alter_column("required_permissions", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("scope_type", existing_type=sa.String(48), nullable=False)
        batch_op.alter_column("scope_id", existing_type=sa.String(160), nullable=False)
        batch_op.create_index(
            "ix_background_jobs_permission_set_version", ["permission_set_version"]
        )
        batch_op.create_index("ix_background_jobs_scope_type", ["scope_type"])
        batch_op.create_index("ix_background_jobs_scope_id", ["scope_id"])


def downgrade() -> None:
    with op.batch_alter_table("background_jobs") as batch_op:
        batch_op.drop_index("ix_background_jobs_scope_id")
        batch_op.drop_index("ix_background_jobs_scope_type")
        batch_op.drop_index("ix_background_jobs_permission_set_version")
        batch_op.drop_column("execution_token_hash")
        batch_op.drop_column("scope_id")
        batch_op.drop_column("scope_type")
        batch_op.drop_column("required_permissions")
        batch_op.drop_column("permission_set_version")
        batch_op.drop_column("actor_snapshot")
