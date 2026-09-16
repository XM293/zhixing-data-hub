"""Add child scenes, warehouse hotspots, and data layers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_spatial_drilldown"
down_revision: str | None = "0002_operational_twin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("twin_scenes") as batch:
        batch.add_column(sa.Column("parent_scene_key", sa.String(100), nullable=True))
        batch.add_column(
            sa.Column("scene_level", sa.String(32), nullable=False, server_default="campus")
        )
        batch.add_column(sa.Column("entry_space_key", sa.String(100), nullable=True))
        batch.add_column(sa.Column("asset_bundle_key", sa.String(120), nullable=True))

    op.create_table(
        "twin_hotspots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("twin_scenes.id"), nullable=False),
        sa.Column("hotspot_key", sa.String(120), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("hotspot_type", sa.String(48), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False),
        sa.Column("business_ref", sa.String(200), nullable=False),
        sa.Column("metric_key", sa.String(100), nullable=True),
        sa.Column("position", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("scene_id", "hotspot_key"),
    )
    op.create_index("ix_twin_hotspots_scene_id", "twin_hotspots", ["scene_id"])
    op.create_table(
        "twin_data_layers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("twin_scenes.id"), nullable=False),
        sa.Column("layer_key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("enabled_default", sa.Boolean(), nullable=False),
        sa.Column("style", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("scene_id", "layer_key"),
    )
    op.create_index("ix_twin_data_layers_scene_id", "twin_data_layers", ["scene_id"])


def downgrade() -> None:
    op.drop_table("twin_data_layers")
    op.drop_table("twin_hotspots")
    with op.batch_alter_table("twin_scenes") as batch:
        batch.drop_column("asset_bundle_key")
        batch.drop_column("entry_space_key")
        batch.drop_column("scene_level")
        batch.drop_column("parent_scene_key")
