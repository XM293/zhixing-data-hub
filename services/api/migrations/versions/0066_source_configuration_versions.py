"""Version source configuration; preserve unknown historical creation and run revisions."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0066_source_configuration_versions"
down_revision = "0065_canonical_fulfillments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("external_systems", sa.Column("version", sa.Integer(),
                                               nullable=False, server_default="1"))
    op.add_column("external_systems", sa.Column("created_at", sa.DateTime(timezone=True)))
    op.add_column("sync_runs", sa.Column("source_version", sa.Integer()))


def downgrade() -> None:
    op.drop_column("sync_runs", "source_version")
    op.drop_column("external_systems", "created_at")
    op.drop_column("external_systems", "version")
