"""Add governed CRM customer profiles and touchpoint facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_customer_360_facts"
down_revision: str | None = "0031_data_scope_mappings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customer_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "external_system_id",
            sa.String(64),
            sa.ForeignKey("external_systems.id"),
            nullable=False,
        ),
        sa.Column("sync_run_id", sa.String(64), sa.ForeignKey("sync_runs.id"), nullable=False),
        sa.Column("customer_key", sa.String(160), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("home_store_key", sa.String(160), nullable=False),
        sa.Column("member_level", sa.String(48), nullable=False),
        sa.Column("lifecycle_stage", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("province", sa.String(80), nullable=False),
        sa.Column("acquisition_channel", sa.String(80), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("member_points", sa.Integer(), nullable=False),
        sa.Column("growth_value", sa.Integer(), nullable=False),
        sa.Column("churn_risk_score", sa.Float(), nullable=False),
        sa.Column("preferred_category", sa.String(120), nullable=False),
        sa.Column("consent_status", sa.String(32), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enterprise_id", "customer_key", name="uq_customer_profile_key"),
    )
    for column in (
        "enterprise_id", "external_system_id", "sync_run_id", "customer_key",
        "home_store_key", "member_level", "lifecycle_stage", "status", "province",
        "acquisition_channel", "registered_at", "last_active_at", "churn_risk_score",
        "preferred_category", "consent_status",
    ):
        op.create_index(f"ix_customer_profiles_{column}", "customer_profiles", [column])

    op.create_table(
        "customer_touchpoint_facts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column(
            "external_system_id",
            sa.String(64),
            sa.ForeignKey("external_systems.id"),
            nullable=False,
        ),
        sa.Column("sync_run_id", sa.String(64), sa.ForeignKey("sync_runs.id"), nullable=False),
        sa.Column("touchpoint_key", sa.String(160), nullable=False),
        sa.Column("customer_key", sa.String(160), nullable=False),
        sa.Column("store_key", sa.String(160), nullable=False),
        sa.Column("touchpoint_type", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("campaign_key", sa.String(160), nullable=True),
        sa.Column("value_fen", sa.BigInteger(), nullable=False),
        sa.Column("properties", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enterprise_id", "touchpoint_key", name="uq_customer_touchpoint_key"),
    )
    for column in (
        "enterprise_id", "external_system_id", "sync_run_id", "touchpoint_key",
        "customer_key", "store_key", "touchpoint_type", "channel", "occurred_at",
        "campaign_key",
    ):
        op.create_index(
            f"ix_customer_touchpoint_facts_{column}",
            "customer_touchpoint_facts",
            [column],
        )


def downgrade() -> None:
    op.drop_table("customer_touchpoint_facts")
    op.drop_table("customer_profiles")
