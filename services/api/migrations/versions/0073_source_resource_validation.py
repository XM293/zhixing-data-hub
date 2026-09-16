"""Persist bounded provider validation evidence for each source resource."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0073_source_resource_validation"
down_revision = "0072_source_backfill_coverage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_resources", sa.Column(
        "validation_status", sa.String(32), nullable=False, server_default="unvalidated"))
    op.add_column("source_resources", sa.Column(
        "validation_run_id", sa.String(64), nullable=True))
    op.add_column("source_resources", sa.Column(
        "validation_error_code", sa.String(120), nullable=True))
    op.add_column("source_resources", sa.Column(
        "last_validated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_source_resources_validation_status", "source_resources",
                    ["validation_status"])
    op.execute(sa.text("""
        WITH ranked AS (
          SELECT rr.source_resource_id, run.id AS run_id, run.status,
                 rr.error_code, COALESCE(run.finished_at, run.started_at) AS validated_at,
                 ROW_NUMBER() OVER (
                   PARTITION BY rr.source_resource_id
                   ORDER BY COALESCE(run.finished_at, run.started_at) DESC, run.id DESC
                 ) AS ordinal
          FROM sync_resource_runs rr
          JOIN sync_runs run ON run.id = rr.sync_run_id
          WHERE run.scenario = 'probe'
            AND run.status IN ('succeeded','failed','partial_failed','cancelled')
        )
        UPDATE source_resources
        SET validation_status = COALESCE((
              SELECT CASE WHEN ranked.status = 'succeeded'
                          THEN 'validated' ELSE 'needs_attention' END
              FROM ranked WHERE ranked.source_resource_id = source_resources.id
                AND ranked.ordinal = 1), 'unvalidated'),
            validation_run_id = (SELECT ranked.run_id FROM ranked
              WHERE ranked.source_resource_id = source_resources.id AND ranked.ordinal = 1),
            validation_error_code = (SELECT ranked.error_code FROM ranked
              WHERE ranked.source_resource_id = source_resources.id AND ranked.ordinal = 1),
            last_validated_at = (SELECT ranked.validated_at FROM ranked
              WHERE ranked.source_resource_id = source_resources.id AND ranked.ordinal = 1)
        WHERE id IN (SELECT source_resource_id FROM ranked WHERE ordinal = 1)
    """))


def downgrade() -> None:
    op.drop_index("ix_source_resources_validation_status", table_name="source_resources")
    op.drop_column("source_resources", "last_validated_at")
    op.drop_column("source_resources", "validation_error_code")
    op.drop_column("source_resources", "validation_run_id")
    op.drop_column("source_resources", "validation_status")
