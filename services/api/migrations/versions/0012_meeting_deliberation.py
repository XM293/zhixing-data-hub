"""Persist two-round meeting deliberation and adversarial risk review."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_meeting_deliberation"
down_revision: str | None = "0011_decision_meetings_and_memory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_deliberation_turns",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("meeting_id", sa.String(64), nullable=False),
        sa.Column("speaker_twin_profile_id", sa.String(64), nullable=False),
        sa.Column("target_twin_profile_id", sa.String(64), nullable=True),
        sa.Column("phase", sa.String(48), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("turn_type", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("new_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("position_after", sa.String(32), nullable=True),
        sa.Column(
            "position_changed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["twin_meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["speaker_twin_profile_id"], ["role_twin_profiles.id"]),
        sa.ForeignKeyConstraint(["target_twin_profile_id"], ["role_twin_profiles.id"]),
        sa.UniqueConstraint(
            "meeting_id",
            "speaker_twin_profile_id",
            "phase",
            name="uq_meeting_deliberation_turn_phase",
        ),
    )
    op.create_index(
        "ix_meeting_deliberation_turns_meeting_id",
        "meeting_deliberation_turns",
        ["meeting_id"],
    )
    op.create_index(
        "ix_meeting_deliberation_turns_speaker_profile",
        "meeting_deliberation_turns",
        ["speaker_twin_profile_id"],
    )
    op.create_index(
        "ix_meeting_deliberation_turns_target_profile",
        "meeting_deliberation_turns",
        ["target_twin_profile_id"],
    )
    op.create_index(
        "ix_meeting_deliberation_turns_phase",
        "meeting_deliberation_turns",
        ["phase"],
    )


def downgrade() -> None:
    op.drop_table("meeting_deliberation_turns")
