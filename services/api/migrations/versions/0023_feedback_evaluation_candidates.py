"""Add governed feedback-to-evaluation candidates."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_feedback_evaluation_candidates"
down_revision: str | None = "0022_evaluation_runner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("source_handoff_case_id", sa.String(64), nullable=False),
        sa.Column("source_feedback_event_id", sa.String(64), nullable=False),
        sa.Column("source_agent_run_id", sa.String(64), nullable=False),
        sa.Column("proposed_case_key", sa.String(120), nullable=False),
        sa.Column("proposed_title", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(48), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("actor_login_name", sa.String(100), nullable=False),
        sa.Column("target_twin_key", sa.String(100), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("expectations", sa.JSON(), nullable=False),
        sa.Column("resolution_summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("proposed_by_principal_id", sa.String(64), nullable=False),
        sa.Column("reviewed_by_principal_id", sa.String(64), nullable=True),
        sa.Column("accepted_case_id", sa.String(64), nullable=True),
        sa.Column("review_reason", sa.Text(), nullable=True),
        sa.Column("review_idempotency_key", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["source_handoff_case_id"], ["human_handoff_cases.id"]),
        sa.ForeignKeyConstraint(["source_feedback_event_id"], ["agent_feedback_events.id"]),
        sa.ForeignKeyConstraint(["source_agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["proposed_by_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["accepted_case_id"], ["evaluation_cases.id"]),
        sa.UniqueConstraint("source_feedback_event_id"),
        sa.UniqueConstraint("review_idempotency_key"),
    )
    for column in (
        "enterprise_id", "source_handoff_case_id", "source_feedback_event_id",
        "source_agent_run_id", "proposed_case_key", "domain", "risk_level",
        "actor_login_name", "target_twin_key", "status", "proposed_by_principal_id",
        "reviewed_by_principal_id", "accepted_case_id", "review_idempotency_key",
        "created_at", "reviewed_at",
    ):
        op.create_index(
            f"ix_evaluation_candidates_{column}", "evaluation_candidates", [column]
        )


def downgrade() -> None:
    op.drop_table("evaluation_candidates")
