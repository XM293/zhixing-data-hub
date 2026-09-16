"""Add the operational digital twin scene projection."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_operational_twin"
down_revision: str | None = "0001_data_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "twin_scenes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("scene_key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("camera_preset", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enterprise_id", "scene_key"),
    )
    op.create_index("ix_twin_scenes_enterprise_id", "twin_scenes", ["enterprise_id"])
    op.create_table(
        "twin_spaces",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("twin_scenes.id"), nullable=False),
        sa.Column("space_key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("space_type", sa.String(48), nullable=False),
        sa.Column("parent_space_key", sa.String(100), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("health", sa.Float(), nullable=False),
        sa.Column("alert_level", sa.String(32), nullable=False),
        sa.Column("metric_key", sa.String(100), nullable=True),
        sa.Column("position", sa.JSON(), nullable=False),
        sa.Column("size", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("scene_id", "space_key"),
    )
    op.create_index("ix_twin_spaces_scene_id", "twin_spaces", ["scene_id"])
    op.create_table(
        "twin_actors",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("actor_key", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("role_title", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("home_space_key", sa.String(100), nullable=False),
        sa.Column("current_space_key", sa.String(100), nullable=False),
        sa.Column("avatar_style", sa.String(64), nullable=False),
        sa.Column("color", sa.String(16), nullable=False),
        sa.Column("position", sa.JSON(), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("enterprise_id", "actor_key"),
    )
    op.create_index("ix_twin_actors_enterprise_id", "twin_actors", ["enterprise_id"])
    op.create_table(
        "twin_routes",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("twin_scenes.id"), nullable=False),
        sa.Column("route_key", sa.String(100), nullable=False),
        sa.Column("source_space_key", sa.String(100), nullable=False),
        sa.Column("target_space_key", sa.String(100), nullable=False),
        sa.Column("route_type", sa.String(48), nullable=False),
        sa.Column("path", sa.JSON(), nullable=False),
        sa.UniqueConstraint("scene_id", "route_key"),
    )
    op.create_index("ix_twin_routes_scene_id", "twin_routes", ["scene_id"])
    op.create_table(
        "twin_meetings",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("twin_scenes.id"), nullable=False),
        sa.Column("meeting_key", sa.String(120), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evidence_snapshot", sa.String(120), nullable=False),
        sa.Column("decision", sa.String(1000), nullable=False),
        sa.Column("room_space_key", sa.String(100), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("enterprise_id", "meeting_key"),
    )
    op.create_index("ix_twin_meetings_enterprise_id", "twin_meetings", ["enterprise_id"])
    op.create_index("ix_twin_meetings_scene_id", "twin_meetings", ["scene_id"])
    op.create_index("ix_twin_meetings_status", "twin_meetings", ["status"])
    op.create_table(
        "twin_meeting_participants",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("meeting_id", sa.String(64), sa.ForeignKey("twin_meetings.id"), nullable=False),
        sa.Column("actor_key", sa.String(100), nullable=False),
        sa.Column("position", sa.String(160), nullable=False),
        sa.Column("finding", sa.String(800), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("speaking_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("meeting_id", "actor_key"),
    )
    op.create_index(
        "ix_twin_meeting_participants_meeting_id",
        "twin_meeting_participants",
        ["meeting_id"],
    )


def downgrade() -> None:
    for table in [
        "twin_meeting_participants",
        "twin_meetings",
        "twin_routes",
        "twin_actors",
        "twin_spaces",
        "twin_scenes",
    ]:
        op.drop_table(table)
