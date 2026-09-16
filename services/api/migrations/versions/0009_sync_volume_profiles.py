"""Persist the requested sandbox volume profile on synchronization runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_sync_volume_profiles"
down_revision: str | None = "0008_data_catalog_quality"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sync_runs",
        sa.Column(
            "volume_profile",
            sa.String(32),
            nullable=False,
            server_default="standard",
        ),
    )


def downgrade() -> None:
    op.drop_column("sync_runs", "volume_profile")
