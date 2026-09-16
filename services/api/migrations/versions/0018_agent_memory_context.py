"""Persist approved memories used by each agent run."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_agent_memory_context"
down_revision: str | None = "0017_memory_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_run_context_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("item_type", sa.String(48), nullable=False),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("version_ref", sa.String(120), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("citation_label", sa.String(400), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("run_id", "item_type", "rank"),
    )
    for column in ("run_id", "item_type", "item_id"):
        op.create_index(f"ix_agent_run_context_items_{column}", "agent_run_context_items", [column])


def downgrade() -> None:
    op.drop_table("agent_run_context_items")
