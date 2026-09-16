"""Coordinate read request budgets across Worker processes without storing secrets."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0060_source_request_budgets"
down_revision = "0059_trusted_scope_selection"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table("source_request_budgets",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("next_allowed_epoch", sa.Numeric(20, 6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_source_request_budgets_updated_at", "source_request_budgets", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_source_request_budgets_updated_at", table_name="source_request_budgets")
    op.drop_table("source_request_budgets")
