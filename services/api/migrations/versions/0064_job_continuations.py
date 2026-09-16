"""Separate successful pagination continuations from failure attempts."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0064_job_continuations"
down_revision = "0063_source_authority_assignments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("continuation_count", "continuation_progress"):
        op.add_column("background_jobs", sa.Column(name, sa.Integer(), nullable=True))
        op.execute(sa.text(f"UPDATE background_jobs SET {name} = 0 WHERE {name} IS NULL"))
        with op.batch_alter_table("background_jobs") as batch:
            batch.alter_column(name, existing_type=sa.Integer(), nullable=False, server_default="0")


def downgrade() -> None:
    # Stop/drain workers before downgrade; retain attempt audit in job_attempts.
    with op.batch_alter_table("background_jobs") as batch:
        batch.drop_column("continuation_progress")
        batch.drop_column("continuation_count")
