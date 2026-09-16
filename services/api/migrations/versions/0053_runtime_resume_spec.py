"""Persist the sanitized Agent Runtime resume specification."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_runtime_resume_spec"
down_revision: str | None = "0052_meeting_runtime_run_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runtime_sessions",
        sa.Column("runtime_spec", sa.JSON(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE agent_runtime_sessions SET runtime_spec = '{}' "
            "WHERE runtime_spec IS NULL"
        )
    )
    with op.batch_alter_table("agent_runtime_sessions") as batch:
        batch.alter_column("runtime_spec", nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("agent_runtime_sessions") as batch:
        batch.drop_column("runtime_spec")
