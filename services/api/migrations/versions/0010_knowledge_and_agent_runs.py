"""Add versioned knowledge, role twins, agent runs, and evidence citations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_knowledge_and_agent_runs"
down_revision: str | None = "0009_sync_volume_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("document_key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("document_type", sa.String(48), nullable=False),
        sa.Column("knowledge_space", sa.String(120), nullable=False),
        sa.Column("source_type", sa.String(48), nullable=False),
        sa.Column("source_uri", sa.String(500), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("owner", sa.String(160), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint("enterprise_id", "document_key", name="uq_knowledge_documents_key"),
    )
    op.create_index(
        "ix_knowledge_documents_enterprise_id", "knowledge_documents", ["enterprise_id"]
    )
    op.create_index("ix_knowledge_documents_status", "knowledge_documents", ["status"])

    op.create_table(
        "knowledge_versions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("version_label", sa.String(40), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("change_summary", sa.String(1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "version_label", name="uq_knowledge_versions_label"),
    )
    op.create_index("ix_knowledge_versions_document_id", "knowledge_versions", ["document_id"])
    op.create_index("ix_knowledge_versions_status", "knowledge_versions", ["status"])
    op.create_index(
        "ix_knowledge_versions_effective_from", "knowledge_versions", ["effective_from"]
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("version_id", sa.String(64), nullable=False),
        sa.Column("chunk_key", sa.String(160), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("heading", sa.String(240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("locator", sa.String(300), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("index_status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_versions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("version_id", "chunk_key", name="uq_knowledge_chunks_key"),
    )
    op.create_index("ix_knowledge_chunks_version_id", "knowledge_chunks", ["version_id"])
    op.create_index("ix_knowledge_chunks_index_status", "knowledge_chunks", ["index_status"])

    op.create_table(
        "role_twin_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("twin_key", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("role_title", sa.String(160), nullable=False),
        sa.Column("voice_guide", sa.Text(), nullable=False),
        sa.Column("reasoning_guide", sa.Text(), nullable=False),
        sa.Column("answer_policy", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint("enterprise_id", "twin_key", name="uq_role_twin_profiles_key"),
    )
    op.create_index("ix_role_twin_profiles_enterprise_id", "role_twin_profiles", ["enterprise_id"])
    op.create_index("ix_role_twin_profiles_status", "role_twin_profiles", ["status"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("twin_profile_id", sa.String(64), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("answer_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("fallback_reason", sa.String(500), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["twin_profile_id"], ["role_twin_profiles.id"]),
    )
    op.create_index("ix_agent_runs_enterprise_id", "agent_runs", ["enterprise_id"])
    op.create_index("ix_agent_runs_twin_profile_id", "agent_runs", ["twin_profile_id"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])
    op.create_index("ix_agent_runs_created_at", "agent_runs", ["created_at"])

    op.create_table(
        "agent_run_evidence",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("chunk_id", sa.String(64), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("citation_label", sa.String(400), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["knowledge_chunks.id"]),
        sa.UniqueConstraint("run_id", "rank", name="uq_agent_run_evidence_rank"),
    )
    op.create_index("ix_agent_run_evidence_run_id", "agent_run_evidence", ["run_id"])
    op.create_index("ix_agent_run_evidence_chunk_id", "agent_run_evidence", ["chunk_id"])


def downgrade() -> None:
    op.drop_table("agent_run_evidence")
    op.drop_table("agent_runs")
    op.drop_table("role_twin_profiles")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_versions")
    op.drop_table("knowledge_documents")
