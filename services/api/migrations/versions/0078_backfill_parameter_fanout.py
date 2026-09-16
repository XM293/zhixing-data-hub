"""Track bounded parameter fanout for each historical coverage window."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0078_backfill_parameter_fanout"
down_revision = "0077_schedule_parameter_fanout"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    backfill_constraints = {item["name"] for item in sa.inspect(
        op.get_bind()).get_check_constraints("source_backfill_plans")}
    with op.batch_alter_table("source_backfill_plans") as batch:
        batch.add_column(sa.Column(
            "parameter_policy_version", sa.String(64), nullable=True))
        batch.add_column(sa.Column(
            "parameter_waiting_code", sa.String(120), nullable=True))
        if "ck_backfill_status" in backfill_constraints:
            batch.drop_constraint("ck_backfill_status", type_="check")
        batch.create_check_constraint(
            "ck_backfill_status",
            "status IN ('paused','active','waiting_for_dependency',"
            "'needs_attention','completed')")
    coverage_constraints = {item["name"] for item in sa.inspect(
        op.get_bind()).get_check_constraints("source_coverage_windows")}
    with op.batch_alter_table("source_coverage_windows") as batch:
        batch.add_column(sa.Column(
            "parameter_fanout_offset", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column(
            "parameter_pending_offset", sa.Integer(), nullable=True))
        batch.add_column(sa.Column(
            "parameter_fanout_total", sa.Integer(), nullable=False, server_default="1"))
        batch.add_column(sa.Column(
            "parameter_cycle_as_of", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint(
            "ck_source_coverage_parameter_offset",
            "parameter_fanout_offset >= 0 AND parameter_fanout_total >= 0 AND "
            "(parameter_pending_offset IS NULL OR parameter_pending_offset >= 0)")
        if "ck_coverage_status" in coverage_constraints:
            batch.drop_constraint("ck_coverage_status", type_="check")
        batch.create_check_constraint(
            "ck_coverage_status",
            "status IN ('fanout_pending','queued','running','succeeded','no_data',"
            "'succeeded_with_conflicts','failed','cancelled')")


def downgrade() -> None:
    with op.batch_alter_table("source_coverage_windows") as batch:
        batch.drop_constraint("ck_coverage_status", type_="check")
        batch.create_check_constraint(
            "ck_coverage_status",
            "status IN ('queued','running','succeeded','no_data',"
            "'succeeded_with_conflicts','failed','cancelled')")
        batch.drop_constraint("ck_source_coverage_parameter_offset", type_="check")
        for name in (
            "parameter_cycle_as_of", "parameter_fanout_total",
            "parameter_pending_offset", "parameter_fanout_offset",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("source_backfill_plans") as batch:
        batch.drop_constraint("ck_backfill_status", type_="check")
        batch.create_check_constraint(
            "ck_backfill_status",
            "status IN ('paused','active','needs_attention','completed')")
        batch.drop_column("parameter_waiting_code")
        batch.drop_column("parameter_policy_version")
