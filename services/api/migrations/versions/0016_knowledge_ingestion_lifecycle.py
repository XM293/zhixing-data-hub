"""Add auditable knowledge ingestion runs and lifecycle events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_knowledge_ingestion_lifecycle"
down_revision: str | None = "0015_enterprise_tool_gateway"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_ingestion_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=True),
        sa.Column("version_id", sa.String(64), nullable=True),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("source_filename", sa.String(260), nullable=False),
        sa.Column("source_type", sa.String(48), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parser_provider", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["version_id"], ["knowledge_versions.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    _indexes(
        "knowledge_ingestion_runs",
        "enterprise_id",
        "document_id",
        "version_id",
        "actor_principal_id",
        "request_id",
        "run_id",
        "content_hash",
        "status",
        "created_at",
    )

    op.create_table(
        "knowledge_lifecycle_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("document_id", sa.String(64), nullable=False),
        sa.Column("version_id", sa.String(64), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["document_id"], ["knowledge_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["version_id"], ["knowledge_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    _indexes(
        "knowledge_lifecycle_events",
        "enterprise_id",
        "document_id",
        "version_id",
        "actor_principal_id",
        "event_type",
        "request_id",
        "run_id",
        "occurred_at",
    )


def downgrade() -> None:
    op.drop_table("knowledge_lifecycle_events")
    op.drop_table("knowledge_ingestion_runs")


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
