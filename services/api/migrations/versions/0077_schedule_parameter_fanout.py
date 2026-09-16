"""Track bounded parameter fanout cycles on recurring source schedules."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0077_schedule_parameter_fanout"
down_revision = "0076_source_dependency_tuples"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_sync_schedules") as batch:
        batch.add_column(sa.Column(
            "parameter_policy_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column(
            "parameter_fanout_offset", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column(
            "parameter_pending_offset", sa.Integer(), nullable=True))
        batch.add_column(sa.Column(
            "parameter_fanout_total", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column(
            "parameter_cycle_as_of", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column(
            "parameter_waiting_code", sa.String(120), nullable=True))
        batch.create_check_constraint(
            "ck_source_schedule_parameter_offset",
            "parameter_fanout_offset >= 0 AND parameter_fanout_total >= 0 AND "
            "(parameter_pending_offset IS NULL OR parameter_pending_offset >= 0)")


def downgrade() -> None:
    with op.batch_alter_table("source_sync_schedules") as batch:
        batch.drop_constraint("ck_source_schedule_parameter_offset", type_="check")
        for name in (
            "parameter_waiting_code", "parameter_cycle_as_of", "parameter_fanout_total",
            "parameter_pending_offset", "parameter_fanout_offset", "parameter_policy_version",
        ):
            batch.drop_column(name)
