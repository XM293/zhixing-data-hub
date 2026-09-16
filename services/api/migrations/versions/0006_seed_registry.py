"""Track versioned seed datasets and detect unversioned drift."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_seed_registry"
down_revision: str | None = "0005_twin_interactions_and_seating"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "seed_versions",
        sa.Column("seed_key", sa.String(120), primary_key=True),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_seed_versions_applied_at", "seed_versions", ["applied_at"])


def downgrade() -> None:
    op.drop_table("seed_versions")
