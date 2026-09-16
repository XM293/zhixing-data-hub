"""Persist Runtime mappings for digital meeting role analysis."""

from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op

revision: str = "0051_meeting_runtime_runs"
down_revision: str | None = "0050_runtime_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_runtime_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("meeting_id", sa.String(64), nullable=False),
        sa.Column("participant_id", sa.String(64), nullable=False),
        sa.Column("agent_run_id", sa.String(64), nullable=False),
        sa.Column("runtime_session_id", sa.String(64), nullable=True),
        sa.Column("evidence_snapshot_id", sa.String(64), nullable=False),
        sa.Column("skill_key", sa.String(100), nullable=False),
        sa.Column("skill_version", sa.Integer(), nullable=False),
        sa.Column("tool_keys", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("failure_code", sa.String(120), nullable=True),
        sa.Column("failure_message", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["meeting_id"], ["twin_meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["participant_id"], ["twin_meeting_participants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["runtime_session_id"], ["agent_runtime_sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["evidence_snapshot_id"], ["evidence_snapshots.id"]),
        sa.UniqueConstraint(
            "meeting_id",
            "participant_id",
            name="uq_meeting_runtime_runs_meeting_id_participant_id",
        ),
    )
    for column in ("enterprise_id", "meeting_id", "participant_id", "agent_run_id", "status", "created_at"):
        op.create_index(f"ix_meeting_runtime_runs_{column}", "meeting_runtime_runs", [column])


def downgrade() -> None:
    op.drop_table("meeting_runtime_runs")
