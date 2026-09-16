"""Persist server-owned meeting transition deadlines."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_meeting_orchestration"
down_revision: str | None = "0003_spatial_drilldown"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("twin_meetings") as batch:
        batch.add_column(sa.Column("next_transition_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_twin_meetings_next_transition_at", ["next_transition_at"])
    op.execute(
        "UPDATE twin_meetings SET next_transition_at = updated_at WHERE status = 'convening'"
    )


def downgrade() -> None:
    with op.batch_alter_table("twin_meetings") as batch:
        batch.drop_index("ix_twin_meetings_next_transition_at")
        batch.drop_column("next_transition_at")
