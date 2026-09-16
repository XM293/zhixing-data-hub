"""Persist the non-secret request context used to acquire each Raw page."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0069_raw_request_context"
down_revision = "0068_source_schedule_parameters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("raw_page_manifests", sa.Column(
        "request_parameters", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    op.drop_column("raw_page_manifests", "request_parameters")
