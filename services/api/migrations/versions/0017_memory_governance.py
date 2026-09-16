"""Add governed chat imports and approved role memories."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_memory_governance"
down_revision: str | None = "0016_knowledge_ingestion_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_import_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("twin_profile_id", sa.String(64), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("source_filename", sa.String(260), nullable=False),
        sa.Column("source_channel", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("topic_count", sa.Integer(), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["twin_profile_id"], ["role_twin_profiles.id"]),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    _indexes(
        "chat_import_runs",
        "enterprise_id",
        "twin_profile_id",
        "actor_principal_id",
        "request_id",
        "run_id",
        "content_hash",
        "status",
        "created_at",
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("import_run_id", sa.String(64), nullable=False),
        sa.Column("message_key", sa.String(120), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sender_name", sa.String(160), nullable=False),
        sa.Column("sender_ref", sa.String(160), nullable=True),
        sa.Column("topic_key", sa.String(120), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["import_run_id"], ["chat_import_runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("import_run_id", "message_key"),
        sa.UniqueConstraint("import_run_id", "ordinal"),
    )
    _indexes("chat_messages", "enterprise_id", "import_run_id", "sender_name", "topic_key")

    op.add_column("memory_candidates", sa.Column("source_import_run_id", sa.String(64), nullable=True))
    op.add_column(
        "memory_candidates",
        sa.Column("evidence_refs", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column("memory_candidates", sa.Column("review_reason", sa.Text(), nullable=True))
    op.add_column("memory_candidates", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_memory_candidates_source_import_run_id",
        "memory_candidates",
        ["source_import_run_id"],
    )

    op.create_table(
        "approved_memories",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("twin_profile_id", sa.String(64), nullable=False),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("memory_key", sa.String(120), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("normalized_hash", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(48), nullable=False),
        sa.Column("source_ref", sa.String(300), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("approved_by_principal_id", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["twin_profile_id"], ["role_twin_profiles.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["memory_candidates.id"]),
        sa.ForeignKeyConstraint(["approved_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "memory_key", "version_number"),
    )
    _indexes(
        "approved_memories",
        "enterprise_id",
        "twin_profile_id",
        "candidate_id",
        "memory_key",
        "normalized_hash",
        "status",
        "approved_by_principal_id",
    )

    op.create_table(
        "memory_review_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("approved_memory_id", sa.String(64), nullable=True),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=False),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["candidate_id"], ["memory_candidates.id"]),
        sa.ForeignKeyConstraint(["approved_memory_id"], ["approved_memories.id"]),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    _indexes(
        "memory_review_events",
        "enterprise_id",
        "candidate_id",
        "approved_memory_id",
        "actor_principal_id",
        "event_type",
        "request_id",
        "run_id",
        "occurred_at",
    )


def downgrade() -> None:
    op.drop_table("memory_review_events")
    op.drop_table("approved_memories")
    op.drop_index("ix_memory_candidates_source_import_run_id", table_name="memory_candidates")
    op.drop_column("memory_candidates", "retired_at")
    op.drop_column("memory_candidates", "review_reason")
    op.drop_column("memory_candidates", "evidence_refs")
    op.drop_column("memory_candidates", "source_import_run_id")
    op.drop_table("chat_messages")
    op.drop_table("chat_import_runs")


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
