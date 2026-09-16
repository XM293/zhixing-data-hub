"""Lingxing source ingestion foundation (additive)."""
from alembic import op
import sqlalchemy as sa
revision="0054_lingxing_ingestion_foundation"; down_revision="0053_runtime_resume_spec"; branch_labels=None; depends_on=None
def upgrade():
    bind=op.get_bind(); insp=sa.inspect(bind)
    if "source_resources" not in insp.get_table_names():
        op.create_table("source_resources", sa.Column("id",sa.String(64),primary_key=True),sa.Column("external_system_id",sa.String(64),sa.ForeignKey("external_systems.id"),nullable=False),sa.Column("resource_key",sa.String(120),nullable=False),sa.Column("method",sa.String(8),nullable=False),sa.Column("path",sa.String(300),nullable=False),sa.Column("schema_status",sa.String(32),server_default="schema_pending"),sa.Column("enabled",sa.Boolean,server_default=sa.true()),sa.UniqueConstraint("external_system_id","resource_key"))
    if "sync_resource_runs" not in insp.get_table_names():
        op.create_table("sync_resource_runs", sa.Column("id",sa.String(64),primary_key=True),sa.Column("sync_run_id",sa.String(64),sa.ForeignKey("sync_runs.id"),nullable=False),sa.Column("source_resource_id",sa.String(64),sa.ForeignKey("source_resources.id"),nullable=False),sa.Column("status",sa.String(32),nullable=False),sa.Column("partition_key",sa.String(160)),sa.Column("records_read",sa.Integer,server_default="0"),sa.Column("records_written",sa.Integer,server_default="0"),sa.Column("error_code",sa.String(120)))
    if "sync_checkpoints" not in insp.get_table_names():
        op.create_table("sync_checkpoints", sa.Column("id",sa.String(64),primary_key=True),sa.Column("source_resource_id",sa.String(64),sa.ForeignKey("source_resources.id"),nullable=False),sa.Column("partition_key",sa.String(160),nullable=False),sa.Column("cursor",sa.String(300)),sa.Column("status",sa.String(32),server_default="active"),sa.UniqueConstraint("source_resource_id","partition_key"))
    if "raw_page_manifests" not in insp.get_table_names():
        op.create_table("raw_page_manifests", sa.Column("id",sa.String(64),primary_key=True),sa.Column("sync_resource_run_id",sa.String(64),sa.ForeignKey("sync_resource_runs.id"),nullable=False),sa.Column("storage_key",sa.String(500),nullable=False),sa.Column("content_hash",sa.String(64),nullable=False),sa.Column("compression",sa.String(24),server_default="gzip"),sa.Column("bytes",sa.BigInteger,server_default="0"),sa.Column("row_count",sa.Integer,server_default="0"),sa.UniqueConstraint("content_hash"))
    if "mapping_conflicts" not in insp.get_table_names():
        op.create_table("mapping_conflicts", sa.Column("id",sa.String(64),primary_key=True),sa.Column("external_system_id",sa.String(64),sa.ForeignKey("external_systems.id"),nullable=False),sa.Column("external_object_key",sa.String(200),nullable=False),sa.Column("status",sa.String(32),server_default="pending"),sa.Column("candidates",sa.JSON,nullable=False),sa.Column("reviewed_by",sa.String(64)),sa.Column("reviewed_at",sa.DateTime(timezone=True)))
    if "source_authority_rules" not in insp.get_table_names():
        op.create_table("source_authority_rules", sa.Column("id",sa.String(64),primary_key=True),sa.Column("enterprise_id",sa.String(64),sa.ForeignKey("enterprises.id"),nullable=False),sa.Column("fact_family",sa.String(80),nullable=False),sa.Column("authority_resource_key",sa.String(120),nullable=False),sa.Column("supplement_resource_keys",sa.JSON,nullable=False),sa.Column("late_arrival_window_hours",sa.Integer,server_default="24"),sa.UniqueConstraint("enterprise_id","fact_family"))
    if "provider_key" not in {c["name"] for c in insp.get_columns("external_systems")}: op.add_column("external_systems",sa.Column("provider_key",sa.String(80),nullable=True)); op.add_column("external_systems",sa.Column("access_mode",sa.String(32),server_default="read_only"))
def downgrade():
    """Remove only objects introduced by 0054, in dependency order."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in (
        "raw_page_manifests",
        "sync_checkpoints",
        "mapping_conflicts",
        "sync_resource_runs",
        "source_authority_rules",
        "source_resources",
    ):
        if table in inspector.get_table_names():
            op.drop_table(table)
    columns = {column["name"] for column in inspector.get_columns("external_systems")}
    if "access_mode" in columns:
        op.drop_column("external_systems", "access_mode")
    if "provider_key" in columns:
        op.drop_column("external_systems", "provider_key")
