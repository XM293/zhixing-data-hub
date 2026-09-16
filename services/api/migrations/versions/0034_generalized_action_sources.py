"""Generalize action proposals beyond digital meeting decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_generalized_action_sources"
down_revision: str | None = "0033_customer_operation_plans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("action_proposals") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_type",
                sa.String(48),
                nullable=False,
                server_default="meeting-decision",
            )
        )
        batch_op.add_column(
            sa.Column("source_key", sa.String(160), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column(
                "source_label",
                sa.String(300),
                nullable=False,
                server_default="数字会议决策",
            )
        )
        batch_op.add_column(
            sa.Column("scope_type", sa.String(32), nullable=False, server_default="object")
        )
        batch_op.add_column(
            sa.Column("scope_key", sa.String(160), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("customer_operation_run_id", sa.String(64), nullable=True))
        batch_op.add_column(sa.Column("evidence_snapshot_id", sa.String(64), nullable=True))
        batch_op.alter_column("meeting_id", existing_type=sa.String(64), nullable=True)
        batch_op.alter_column(
            "decision_package_id", existing_type=sa.String(64), nullable=True
        )
        batch_op.create_foreign_key(
            "fk_action_proposals_customer_operation_run",
            "customer_operation_runs",
            ["customer_operation_run_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_action_proposals_evidence_snapshot",
            "evidence_snapshots",
            ["evidence_snapshot_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_action_customer_operation_step",
            ["customer_operation_run_id", "source_action_index"],
        )

    op.execute(
        sa.text(
            """
            UPDATE action_proposals
            SET source_key = COALESCE(
                    (SELECT meeting_key FROM twin_meetings
                     WHERE twin_meetings.id = action_proposals.meeting_id),
                    proposal_key
                ),
                source_label = COALESCE(
                    (SELECT title FROM twin_meetings
                     WHERE twin_meetings.id = action_proposals.meeting_id),
                    '数字会议决策'
                ),
                scope_type = 'object',
                scope_key = COALESCE(
                    (SELECT meeting_key FROM twin_meetings
                     WHERE twin_meetings.id = action_proposals.meeting_id),
                    proposal_key
                )
            """
        )
    )
    for name, columns in (
        ("ix_action_proposals_source_type", ["source_type"]),
        ("ix_action_proposals_source_key", ["source_key"]),
        ("ix_action_proposals_scope_type", ["scope_type"]),
        ("ix_action_proposals_scope_key", ["scope_key"]),
        ("ix_action_proposals_customer_operation_run_id", ["customer_operation_run_id"]),
        ("ix_action_proposals_evidence_snapshot_id", ["evidence_snapshot_id"]),
    ):
        op.create_index(name, "action_proposals", columns)


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM action_executions
            WHERE proposal_id IN (
                SELECT id FROM action_proposals WHERE source_type = 'customer-operation'
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM action_approval_events
            WHERE proposal_id IN (
                SELECT id FROM action_proposals WHERE source_type = 'customer-operation'
            )
            """
        )
    )
    op.execute(
        sa.text("DELETE FROM action_proposals WHERE source_type = 'customer-operation'")
    )
    for name in (
        "ix_action_proposals_evidence_snapshot_id",
        "ix_action_proposals_customer_operation_run_id",
        "ix_action_proposals_scope_key",
        "ix_action_proposals_scope_type",
        "ix_action_proposals_source_key",
        "ix_action_proposals_source_type",
    ):
        op.drop_index(name, table_name="action_proposals")
    with op.batch_alter_table("action_proposals") as batch_op:
        batch_op.drop_constraint("uq_action_customer_operation_step", type_="unique")
        batch_op.drop_constraint(
            "fk_action_proposals_evidence_snapshot", type_="foreignkey"
        )
        batch_op.drop_constraint(
            "fk_action_proposals_customer_operation_run", type_="foreignkey"
        )
        batch_op.alter_column("meeting_id", existing_type=sa.String(64), nullable=False)
        batch_op.alter_column(
            "decision_package_id", existing_type=sa.String(64), nullable=False
        )
        batch_op.drop_column("evidence_snapshot_id")
        batch_op.drop_column("customer_operation_run_id")
        batch_op.drop_column("scope_key")
        batch_op.drop_column("scope_type")
        batch_op.drop_column("source_label")
        batch_op.drop_column("source_key")
        batch_op.drop_column("source_type")
