"""Add governed knowledge provider dual-run evaluation ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_knowledge_provider_evaluations"
down_revision: str | None = "0028_memory_provider_evaluations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_provider_evaluation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "actor_principal_id",
            sa.String(64),
            sa.ForeignKey("principals.id"),
            nullable=False,
        ),
        sa.Column("evaluation_key", sa.String(120), nullable=False),
        sa.Column("benchmark_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider_keys", sa.JSON(), nullable=False),
        sa.Column("benchmark_snapshot", sa.JSON(), nullable=False),
        sa.Column("document_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "enterprise_id",
            "idempotency_key",
            name="uq_knowledge_provider_evaluation_enterprise_idempotency",
        ),
    )
    for column in (
        "enterprise_id",
        "actor_principal_id",
        "evaluation_key",
        "status",
        "idempotency_key",
        "request_id",
        "run_id",
        "created_at",
    ):
        op.create_index(
            f"ix_knowledge_provider_evaluation_runs_{column}",
            "knowledge_provider_evaluation_runs",
            [column],
        )

    op.create_table(
        "knowledge_provider_evaluation_results",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "evaluation_run_id",
            sa.String(64),
            sa.ForeignKey("knowledge_provider_evaluation_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_key", sa.String(64), nullable=False),
        sa.Column("provider_mode", sa.String(48), nullable=False),
        sa.Column("protocol", sa.String(80), nullable=False),
        sa.Column("endpoint_fingerprint", sa.String(24), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("indexed_document_count", sa.Integer(), nullable=False),
        sa.Column("indexed_chunk_count", sa.Integer(), nullable=False),
        sa.Column("query_count", sa.Integer(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("recall_at_k", sa.Float(), nullable=False),
        sa.Column("mean_reciprocal_rank", sa.Float(), nullable=False),
        sa.Column("average_latency_ms", sa.Integer(), nullable=False),
        sa.Column("p95_latency_ms", sa.Integer(), nullable=False),
        sa.Column("result_items", sa.JSON(), nullable=False),
        sa.Column("failure_reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "evaluation_run_id",
            "provider_key",
            name="uq_knowledge_provider_evaluation_result_provider",
        ),
    )
    for column in ("evaluation_run_id", "provider_key", "status", "created_at"):
        op.create_index(
            f"ix_knowledge_provider_evaluation_results_{column}",
            "knowledge_provider_evaluation_results",
            [column],
        )


def downgrade() -> None:
    op.drop_table("knowledge_provider_evaluation_results")
    op.drop_table("knowledge_provider_evaluation_runs")
