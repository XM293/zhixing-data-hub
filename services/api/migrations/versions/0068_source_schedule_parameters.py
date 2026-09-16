"""Persist validated resource partitions on recurring source schedules."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0068_source_schedule_parameters"
down_revision = "0067_source_mirror_pages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_sync_schedules", sa.Column(
        "resource_parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    op.drop_column("source_sync_schedules", "resource_parameters")
