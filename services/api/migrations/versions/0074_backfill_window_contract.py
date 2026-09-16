"""Allow documented source backfill windows up to 366 days."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0074_backfill_window_contract"
down_revision = "0073_source_resource_validation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    names = {item["name"] for item in sa.inspect(op.get_bind()).get_check_constraints(
        "source_backfill_plans")}
    with op.batch_alter_table("source_backfill_plans") as batch:
        if "ck_backfill_partition_days" in names:
            batch.drop_constraint("ck_backfill_partition_days", type_="check")
        batch.create_check_constraint(
            "ck_backfill_partition_days", "partition_days BETWEEN 1 AND 366")


def downgrade() -> None:
    names = {item["name"] for item in sa.inspect(op.get_bind()).get_check_constraints(
        "source_backfill_plans")}
    with op.batch_alter_table("source_backfill_plans") as batch:
        if "ck_backfill_partition_days" in names:
            batch.drop_constraint("ck_backfill_partition_days", type_="check")
        batch.create_check_constraint(
            "ck_backfill_partition_days", "partition_days BETWEEN 1 AND 7")
