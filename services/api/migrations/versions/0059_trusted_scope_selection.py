"""Persist only validated session scope selection; null preserves existing sessions."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0059_trusted_scope_selection"
down_revision = "0058_canonical_source_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("scope_selection", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_sessions", "scope_selection")
