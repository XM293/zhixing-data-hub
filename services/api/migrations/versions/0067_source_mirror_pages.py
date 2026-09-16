"""Separate durable acquisition receipts from offline projection runs."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0067_source_mirror_pages"
down_revision = "0066_source_configuration_versions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("source_sync_schedules", sa.Column("projection_mode", sa.String(20),
                                                   nullable=False, server_default="inline"))
    op.create_table("source_mirror_pages",
        sa.Column("raw_manifest_id", sa.String(120), sa.ForeignKey("raw_page_manifests.id"),
                  primary_key=True),
        sa.Column("enterprise_id", sa.String(120), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("source_resource_id", sa.String(120), sa.ForeignKey("source_resources.id"),
                  nullable=False),
        sa.Column("acquisition_run_id", sa.String(120), sa.ForeignKey("sync_runs.id"),
                  nullable=False),
        sa.Column("projection_run_id", sa.String(120), sa.ForeignKey("sync_runs.id"), unique=True),
        sa.Column("schema_status", sa.String(40), nullable=False),
        sa.Column("mapping_version", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    for column in ("enterprise_id", "source_resource_id", "acquisition_run_id"):
        op.create_index(f"ix_source_mirror_pages_{column}", "source_mirror_pages", [column])


def downgrade() -> None:
    op.drop_table("source_mirror_pages")
    op.drop_column("source_sync_schedules", "projection_mode")
