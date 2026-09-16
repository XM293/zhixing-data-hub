"""Add evidence snapshots, governed memories, and structured decision meetings."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_decision_meetings_and_memory"
down_revision: str | None = "0010_knowledge_and_agent_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("twin_meetings") as batch:
        batch.add_column(
            sa.Column(
                "protocol_status",
                sa.String(32),
                nullable=False,
                server_default="draft",
            )
        )
        batch.add_column(
            sa.Column(
                "template_key",
                sa.String(100),
                nullable=False,
                server_default="budget-inventory-review",
            )
        )
        batch.add_column(
            sa.Column(
                "decision_owner",
                sa.String(160),
                nullable=False,
                server_default="CEO",
            )
        )
        batch.add_column(sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column(
                "success_metric",
                sa.String(500),
                nullable=False,
                server_default="等待定义",
            )
        )
        batch.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch.create_index("ix_twin_meetings_protocol_status", ["protocol_status"])

    op.create_table(
        "evidence_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("snapshot_key", sa.String(120), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint("enterprise_id", "snapshot_key", name="uq_evidence_snapshots_key"),
    )
    op.create_index("ix_evidence_snapshots_enterprise_id", "evidence_snapshots", ["enterprise_id"])
    op.create_index("ix_evidence_snapshots_purpose", "evidence_snapshots", ["purpose"])

    op.create_table(
        "evidence_snapshot_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("snapshot_id", sa.String(64), nullable=False),
        sa.Column("item_type", sa.String(48), nullable=False),
        sa.Column("item_key", sa.String(160), nullable=False),
        sa.Column("version_ref", sa.String(120), nullable=True),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["evidence_snapshots.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("snapshot_id", "rank", name="uq_evidence_snapshot_items_rank"),
    )
    op.create_index(
        "ix_evidence_snapshot_items_snapshot_id",
        "evidence_snapshot_items",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_evidence_snapshot_items_item_type",
        "evidence_snapshot_items",
        ["item_type"],
    )

    op.create_table(
        "memory_candidates",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("twin_profile_id", sa.String(64), nullable=False),
        sa.Column("candidate_key", sa.String(120), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(48), nullable=False),
        sa.Column("source_ref", sa.String(300), nullable=False),
        sa.Column("normalized_hash", sa.String(64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("conflict_status", sa.String(32), nullable=False),
        sa.Column("conflict_ref", sa.String(300), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reviewer", sa.String(160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["twin_profile_id"], ["role_twin_profiles.id"]),
        sa.UniqueConstraint("enterprise_id", "candidate_key", name="uq_memory_candidates_key"),
    )
    op.create_index("ix_memory_candidates_enterprise_id", "memory_candidates", ["enterprise_id"])
    op.create_index(
        "ix_memory_candidates_twin_profile_id",
        "memory_candidates",
        ["twin_profile_id"],
    )
    op.create_index("ix_memory_candidates_status", "memory_candidates", ["status"])

    op.create_table(
        "meeting_claims",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("meeting_id", sa.String(64), nullable=False),
        sa.Column("twin_profile_id", sa.String(64), nullable=False),
        sa.Column("phase", sa.String(48), nullable=False),
        sa.Column("stance", sa.String(32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("unknowns", sa.JSON(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["twin_meetings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["twin_profile_id"], ["role_twin_profiles.id"]),
        sa.UniqueConstraint(
            "meeting_id", "twin_profile_id", "phase", name="uq_meeting_claims_phase"
        ),
    )
    op.create_index("ix_meeting_claims_meeting_id", "meeting_claims", ["meeting_id"])
    op.create_index("ix_meeting_claims_twin_profile_id", "meeting_claims", ["twin_profile_id"])

    op.create_table(
        "decision_packages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("meeting_id", sa.String(64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("consensus", sa.JSON(), nullable=False),
        sa.Column("disagreements", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["meeting_id"], ["twin_meetings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("meeting_id", name="uq_decision_packages_meeting"),
    )
    op.create_index("ix_decision_packages_meeting_id", "decision_packages", ["meeting_id"])
    op.create_index("ix_decision_packages_status", "decision_packages", ["status"])

    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("meeting_id", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("run_type", sa.String(32), nullable=False, server_default="answer")
        )
        batch.add_column(sa.Column("phase", sa.String(48), nullable=True))
        batch.create_foreign_key(
            "fk_agent_runs_meeting_id", "twin_meetings", ["meeting_id"], ["id"]
        )
        batch.create_index("ix_agent_runs_meeting_id", ["meeting_id"])
        batch.create_index("ix_agent_runs_run_type", ["run_type"])


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_index("ix_agent_runs_run_type")
        batch.drop_index("ix_agent_runs_meeting_id")
        batch.drop_constraint("fk_agent_runs_meeting_id", type_="foreignkey")
        batch.drop_column("phase")
        batch.drop_column("run_type")
        batch.drop_column("meeting_id")
    op.drop_table("decision_packages")
    op.drop_table("meeting_claims")
    op.drop_table("memory_candidates")
    op.drop_table("evidence_snapshot_items")
    op.drop_table("evidence_snapshots")
    with op.batch_alter_table("twin_meetings") as batch:
        batch.drop_index("ix_twin_meetings_protocol_status")
        batch.drop_column("created_at")
        batch.drop_column("success_metric")
        batch.drop_column("deadline_at")
        batch.drop_column("decision_owner")
        batch.drop_column("template_key")
        batch.drop_column("protocol_status")
