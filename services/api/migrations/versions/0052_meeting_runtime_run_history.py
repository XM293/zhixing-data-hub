"""Keep every Runtime-backed meeting run for audit history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0052_meeting_runtime_run_history"
down_revision: str | None = "0051_meeting_runtime_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("meeting_runtime_runs") as batch:
        batch.drop_constraint(
            "uq_meeting_runtime_runs_meeting_id_participant_id",
            type_="unique",
        )
        batch.create_unique_constraint(
            "uq_meeting_runtime_runs_meeting_participant_agent_run",
            ["meeting_id", "participant_id", "agent_run_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("meeting_runtime_runs") as batch:
        batch.drop_constraint(
            "uq_meeting_runtime_runs_meeting_participant_agent_run",
            type_="unique",
        )
        batch.create_unique_constraint(
            "uq_meeting_runtime_runs_meeting_id_participant_id",
            ["meeting_id", "participant_id"],
        )
