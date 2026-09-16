"""Add governed scheduled store review plans and runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_scheduled_store_reviews"
down_revision: str | None = "0035_operational_work_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_PERMISSIONS = (
    (
        "permission_analysis_schedule_read",
        "analysis.schedule.read",
        "读取经营巡店计划与运行",
        "analysis.schedule",
        "read",
        "R0",
    ),
    (
        "permission_analysis_schedule_manage",
        "analysis.schedule.manage",
        "管理经营巡店计划",
        "analysis.schedule",
        "manage",
        "R2",
    ),
)

ROLE_PERMISSION_KEYS = {
    "role_executive_v1": ("analysis.schedule.read", "analysis.schedule.manage"),
    "role_operations_manager_v1": (
        "analysis.schedule.read",
        "analysis.schedule.manage",
    ),
    "role_employee_v1": ("analysis.schedule.read",),
    "role_platform_admin_v1": ("analysis.schedule.read",),
    "role_finance_controller_v1": ("analysis.schedule.read",),
}


def upgrade() -> None:
    op.create_table(
        "store_review_plans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("plan_key", sa.String(160), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("scope_label", sa.String(200), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("local_time", sa.String(5), nullable=False),
        sa.Column("weekdays", sa.JSON(), nullable=False),
        sa.Column("auto_propose_min_priority", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_enqueued_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_principal_id", sa.String(64), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("last_action", sa.String(24)),
        sa.Column("last_action_idempotency_key", sa.String(200)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "plan_key"),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    _indexes(
        "store_review_plans",
        "enterprise_id",
        "plan_key",
        "scope_type",
        "scope_key",
        "status",
        "next_run_at",
        "created_by_principal_id",
        "idempotency_key",
        "last_action_idempotency_key",
        "created_at",
        "updated_at",
    )

    op.create_table(
        "store_review_schedule_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(64), nullable=False),
        sa.Column("business_date", sa.Date(), nullable=False),
        sa.Column("trigger_type", sa.String(24), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("background_job_id", sa.String(64)),
        sa.Column("analysis_run_id", sa.String(64)),
        sa.Column("brief_id", sa.String(64)),
        sa.Column("proposal_count", sa.Integer(), nullable=False),
        sa.Column("execution_mode", sa.String(32)),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("error_code", sa.String(120)),
        sa.Column("error_message", sa.String(1000)),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["store_review_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["background_job_id"], ["background_jobs.id"]),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["business_analysis_runs.id"]),
        sa.ForeignKeyConstraint(["brief_id"], ["business_briefs.id"]),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
        sa.UniqueConstraint("background_job_id"),
    )
    _indexes(
        "store_review_schedule_runs",
        "enterprise_id",
        "plan_id",
        "business_date",
        "trigger_type",
        "idempotency_key",
        "status",
        "background_job_id",
        "analysis_run_id",
        "brief_id",
        "request_id",
        "run_id",
        "queued_at",
        "completed_at",
    )

    permission_table = sa.table(
        "permission_definitions",
        sa.column("id", sa.String),
        sa.column("permission_key", sa.String),
        sa.column("label", sa.String),
        sa.column("resource", sa.String),
        sa.column("action", sa.String),
        sa.column("risk_level", sa.String),
        sa.column("status", sa.String),
    )
    op.bulk_insert(
        permission_table,
        [
            {
                "id": item[0],
                "permission_key": item[1],
                "label": item[2],
                "resource": item[3],
                "action": item[4],
                "risk_level": item[5],
                "status": "active",
            }
            for item in NEW_PERMISSIONS
        ],
    )
    _grant_existing_roles()


def downgrade() -> None:
    op.drop_table("store_review_schedule_runs")
    op.drop_table("store_review_plans")
    connection = op.get_bind()
    permission_ids = [item[0] for item in NEW_PERMISSIONS]
    connection.execute(
        sa.text(
            "DELETE FROM access_role_permissions WHERE permission_id IN "
            "(:read_id, :manage_id)"
        ),
        {"read_id": permission_ids[0], "manage_id": permission_ids[1]},
    )
    connection.execute(
        sa.text(
            "DELETE FROM permission_definitions WHERE id IN (:read_id, :manage_id)"
        ),
        {"read_id": permission_ids[0], "manage_id": permission_ids[1]},
    )


def _grant_existing_roles() -> None:
    connection = op.get_bind()
    permission_ids = {item[1]: item[0] for item in NEW_PERMISSIONS}
    for role_id, permission_keys in ROLE_PERMISSION_KEYS.items():
        exists = connection.execute(
            sa.text("SELECT 1 FROM access_roles WHERE id = :role_id"),
            {"role_id": role_id},
        ).scalar_one_or_none()
        if not exists:
            continue
        for permission_key in permission_keys:
            normalized = permission_key.replace(".", "_")
            connection.execute(
                sa.text(
                    "INSERT INTO access_role_permissions "
                    "(id, access_role_id, permission_id, effect) "
                    "VALUES (:id, :role_id, :permission_id, 'allow')"
                ),
                {
                    "id": f"role_permission_{role_id}_{normalized}",
                    "role_id": role_id,
                    "permission_id": permission_ids[permission_key],
                },
            )


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
