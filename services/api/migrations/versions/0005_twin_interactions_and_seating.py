"""Persist spatial interaction profiles and scalable meeting seating."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_twin_interactions_and_seating"
down_revision: str | None = "0004_meeting_orchestration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Alembic defaults version_num to varchar(32); this revision name is longer.
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(32),
            type_=sa.String(128),
            existing_nullable=False,
        )

    with op.batch_alter_table("twin_meeting_participants") as batch:
        batch.add_column(sa.Column("seat_key", sa.String(100), nullable=True))

    op.create_table(
        "twin_meeting_seats",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scene_id", sa.String(64), sa.ForeignKey("twin_scenes.id"), nullable=False),
        sa.Column("seat_key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("layout_key", sa.String(64), nullable=False),
        sa.Column("position", sa.JSON(), nullable=False),
        sa.Column("rotation_y", sa.Float(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("scene_id", "seat_key"),
    )
    op.create_index("ix_twin_meeting_seats_scene_id", "twin_meeting_seats", ["scene_id"])

    op.create_table(
        "twin_interaction_profiles",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), sa.ForeignKey("enterprises.id"), nullable=False),
        sa.Column("entity_key", sa.String(120), nullable=False),
        sa.Column("entity_type", sa.String(48), nullable=False),
        sa.Column("detail_route", sa.String(300), nullable=True),
        sa.Column("enter_space_key", sa.String(100), nullable=True),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("enterprise_id", "entity_key"),
    )
    op.create_index(
        "ix_twin_interaction_profiles_enterprise_id",
        "twin_interaction_profiles",
        ["enterprise_id"],
    )


def downgrade() -> None:
    op.drop_table("twin_interaction_profiles")
    op.drop_table("twin_meeting_seats")
    with op.batch_alter_table("twin_meeting_participants") as batch:
        batch.drop_column("seat_key")
