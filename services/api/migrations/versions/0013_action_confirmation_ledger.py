"""Persist human decision confirmation and controlled action ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_action_confirmation_ledger"
down_revision: str | None = "0012_meeting_deliberation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_decision_confirmations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("meeting_id", sa.String(64), nullable=False),
        sa.Column("decision_package_id", sa.String(64), nullable=False),
        sa.Column("confirmed_by_actor_key", sa.String(120), nullable=False),
        sa.Column("confirmed_by_name", sa.String(160), nullable=False),
        sa.Column("actor_context", sa.JSON(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["meeting_id"], ["twin_meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["decision_package_id"], ["decision_packages.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("meeting_id"),
        sa.UniqueConstraint("decision_package_id"),
    )
    op.create_index(
        "ix_meeting_decision_confirmations_enterprise_id",
        "meeting_decision_confirmations",
        ["enterprise_id"],
    )
    op.create_index(
        "ix_meeting_decision_confirmations_meeting_id",
        "meeting_decision_confirmations",
        ["meeting_id"],
    )
    op.create_index(
        "ix_meeting_decision_confirmations_package_id",
        "meeting_decision_confirmations",
        ["decision_package_id"],
    )
    op.create_index(
        "ix_meeting_decision_confirmations_actor_key",
        "meeting_decision_confirmations",
        ["confirmed_by_actor_key"],
    )

    op.create_table(
        "action_proposals",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("proposal_key", sa.String(160), nullable=False),
        sa.Column("meeting_id", sa.String(64), nullable=False),
        sa.Column("decision_package_id", sa.String(64), nullable=False),
        sa.Column("source_action_index", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("owner", sa.String(160), nullable=False),
        sa.Column("due_hint", sa.String(300), nullable=False),
        sa.Column("kpi", sa.Text(), nullable=False),
        sa.Column("stop_condition", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("target_system", sa.String(120), nullable=False),
        sa.Column("target_key", sa.String(200), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("action_level", sa.String(16), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("requested_by_actor_key", sa.String(120), nullable=False),
        sa.Column("requested_by_name", sa.String(160), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("approved_by_actor_key", sa.String(120), nullable=True),
        sa.Column("approved_by_name", sa.String(160), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["meeting_id"], ["twin_meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["decision_package_id"], ["decision_packages.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("enterprise_id", "proposal_key"),
        sa.UniqueConstraint("decision_package_id", "source_action_index"),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    for name, columns in (
        ("ix_action_proposals_enterprise_id", ["enterprise_id"]),
        ("ix_action_proposals_proposal_key", ["proposal_key"]),
        ("ix_action_proposals_meeting_id", ["meeting_id"]),
        ("ix_action_proposals_decision_package_id", ["decision_package_id"]),
        ("ix_action_proposals_status", ["status"]),
        ("ix_action_proposals_risk_level", ["risk_level"]),
        ("ix_action_proposals_requested_by", ["requested_by_actor_key"]),
        ("ix_action_proposals_approved_by", ["approved_by_actor_key"]),
        ("ix_action_proposals_idempotency_key", ["idempotency_key"]),
        ("ix_action_proposals_created_at", ["created_at"]),
    ):
        op.create_index(name, "action_proposals", columns)

    op.create_table(
        "action_approval_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=False),
        sa.Column("actor_key", sa.String(120), nullable=False),
        sa.Column("actor_name", sa.String(160), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("actor_context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["action_proposals.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    for name, columns in (
        ("ix_action_approval_events_enterprise_id", ["enterprise_id"]),
        ("ix_action_approval_events_proposal_id", ["proposal_id"]),
        ("ix_action_approval_events_actor_key", ["actor_key"]),
        ("ix_action_approval_events_decision", ["decision"]),
        ("ix_action_approval_events_idempotency_key", ["idempotency_key"]),
        ("ix_action_approval_events_created_at", ["created_at"]),
    ):
        op.create_index(name, "action_approval_events", columns)

    op.create_table(
        "action_executions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("execution_key", sa.String(160), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("external_write", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("actor_key", sa.String(120), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["action_proposals.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("enterprise_id", "execution_key"),
        sa.UniqueConstraint("proposal_id"),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    for name, columns in (
        ("ix_action_executions_enterprise_id", ["enterprise_id"]),
        ("ix_action_executions_execution_key", ["execution_key"]),
        ("ix_action_executions_proposal_id", ["proposal_id"]),
        ("ix_action_executions_idempotency_key", ["idempotency_key"]),
        ("ix_action_executions_status", ["status"]),
    ):
        op.create_index(name, "action_executions", columns)


def downgrade() -> None:
    op.drop_table("action_executions")
    op.drop_table("action_approval_events")
    op.drop_table("action_proposals")
    op.drop_table("meeting_decision_confirmations")
