"""Add attributable agent feedback and human handoff cases."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_agent_feedback_and_handoff"
down_revision: str | None = "0020_role_twin_test_studio"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.add_column(sa.Column("actor_principal_id", sa.String(64), nullable=True))
        batch_op.create_foreign_key(
            "fk_agent_runs_actor_principal_id",
            "principals",
            ["actor_principal_id"],
            ["id"],
        )
        batch_op.create_index("ix_agent_runs_actor_principal_id", ["actor_principal_id"])

    op.create_table(
        "human_handoff_cases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("agent_run_id", sa.String(64), nullable=False),
        sa.Column("opened_by_principal_id", sa.String(64), nullable=False),
        sa.Column("assigned_to_principal_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("priority", sa.String(32), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("subject", sa.String(240), nullable=False),
        sa.Column("resolution_type", sa.String(48), nullable=True),
        sa.Column("resolution_summary", sa.Text(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(["opened_by_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["assigned_to_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "agent_run_id", "opened_by_principal_id"),
    )
    for column in (
        "enterprise_id",
        "agent_run_id",
        "opened_by_principal_id",
        "assigned_to_principal_id",
        "status",
        "priority",
        "category",
        "opened_at",
        "updated_at",
        "resolved_at",
    ):
        op.create_index(f"ix_human_handoff_cases_{column}", "human_handoff_cases", [column])

    op.create_table(
        "agent_feedback_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("agent_run_id", sa.String(64), nullable=False),
        sa.Column("handoff_case_id", sa.String(64), nullable=True),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("feedback_kind", sa.String(32), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=True),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.ForeignKeyConstraint(
            ["handoff_case_id"], ["human_handoff_cases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    for column in (
        "enterprise_id",
        "agent_run_id",
        "handoff_case_id",
        "actor_principal_id",
        "event_type",
        "feedback_kind",
        "idempotency_key",
        "request_id",
        "run_id",
        "created_at",
    ):
        op.create_index(f"ix_agent_feedback_events_{column}", "agent_feedback_events", [column])


def downgrade() -> None:
    op.drop_table("agent_feedback_events")
    op.drop_table("human_handoff_cases")
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_index("ix_agent_runs_actor_principal_id")
        batch_op.drop_constraint("fk_agent_runs_actor_principal_id", type_="foreignkey")
        batch_op.drop_column("actor_principal_id")
