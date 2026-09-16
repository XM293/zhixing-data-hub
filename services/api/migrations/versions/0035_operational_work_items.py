"""Connect analysis recommendations to governed internal work items."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0035_operational_work_items"
down_revision: str | None = "0034_generalized_action_sources"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_PERMISSIONS = (
    (
        "permission_action_work_read",
        "action.work.read",
        "读取授权范围内行动工作项",
        "action.work",
        "read",
        "R0",
    ),
    (
        "permission_action_work_update",
        "action.work.update",
        "更新本人领取的行动工作项",
        "action.work",
        "update",
        "R1",
    ),
    (
        "permission_action_work_manage",
        "action.work.manage",
        "管理授权范围内行动工作项",
        "action.work",
        "manage",
        "R2",
    ),
)

ROLE_PERMISSION_KEYS = {
    "role_executive_v1": ("action.work.read",),
    "role_operations_manager_v1": (
        "action.work.read",
        "action.work.update",
        "action.work.manage",
    ),
    "role_employee_v1": ("action.work.read", "action.work.update"),
    "role_finance_controller_v1": ("action.work.read",),
}


def upgrade() -> None:
    with op.batch_alter_table("action_proposals") as batch_op:
        batch_op.add_column(sa.Column("business_analysis_run_id", sa.String(64)))
        batch_op.create_foreign_key(
            "fk_action_proposals_business_analysis_run",
            "business_analysis_runs",
            ["business_analysis_run_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_action_business_analysis_step",
            ["business_analysis_run_id", "source_action_index"],
        )
    op.create_index(
        "ix_action_proposals_business_analysis_run_id",
        "action_proposals",
        ["business_analysis_run_id"],
    )

    op.create_table(
        "action_work_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("work_key", sa.String(200), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("scope_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assignee_principal_id", sa.String(64)),
        sa.Column("assignee_name", sa.String(160)),
        sa.Column("owner_role", sa.String(160), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("due_hint", sa.String(300), nullable=False),
        sa.Column("kpi", sa.Text(), nullable=False),
        sa.Column("stop_condition", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("blocked_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("blocker_reason", sa.Text()),
        sa.Column("result_summary", sa.Text()),
        sa.Column("result_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["proposal_id"], ["action_proposals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "work_key"),
        sa.UniqueConstraint("proposal_id"),
    )
    _indexes(
        "action_work_items",
        "enterprise_id",
        "work_key",
        "proposal_id",
        "scope_type",
        "scope_key",
        "status",
        "assignee_principal_id",
        "priority",
        "created_at",
        "updated_at",
    )

    op.create_table(
        "action_work_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("work_item_id", sa.String(64), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(160), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(32)),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(
            ["work_item_id"], ["action_work_items.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "idempotency_key"),
    )
    _indexes(
        "action_work_events",
        "enterprise_id",
        "work_item_id",
        "actor_principal_id",
        "event_type",
        "to_status",
        "idempotency_key",
        "created_at",
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
    _backfill_approved_work_items()


def downgrade() -> None:
    op.drop_table("action_work_events")
    op.drop_table("action_work_items")
    connection = op.get_bind()
    permission_ids = [item[0] for item in NEW_PERMISSIONS]
    connection.execute(
        sa.text(
            "DELETE FROM access_role_permissions WHERE permission_id IN "
            "(:read_id, :update_id, :manage_id)"
        ),
        {
            "read_id": permission_ids[0],
            "update_id": permission_ids[1],
            "manage_id": permission_ids[2],
        },
    )
    connection.execute(
        sa.text(
            "DELETE FROM permission_definitions WHERE id IN "
            "(:read_id, :update_id, :manage_id)"
        ),
        {
            "read_id": permission_ids[0],
            "update_id": permission_ids[1],
            "manage_id": permission_ids[2],
        },
    )
    connection.execute(
        sa.text(
            "DELETE FROM action_executions WHERE proposal_id IN "
            "(SELECT id FROM action_proposals WHERE source_type = 'business-analysis')"
        )
    )
    connection.execute(
        sa.text(
            "DELETE FROM action_approval_events WHERE proposal_id IN "
            "(SELECT id FROM action_proposals WHERE source_type = 'business-analysis')"
        )
    )
    connection.execute(
        sa.text("DELETE FROM action_proposals WHERE source_type = 'business-analysis'")
    )
    op.drop_index(
        "ix_action_proposals_business_analysis_run_id",
        table_name="action_proposals",
    )
    with op.batch_alter_table("action_proposals") as batch_op:
        batch_op.drop_constraint("uq_action_business_analysis_step", type_="unique")
        batch_op.drop_constraint(
            "fk_action_proposals_business_analysis_run", type_="foreignkey"
        )
        batch_op.drop_column("business_analysis_run_id")


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


def _backfill_approved_work_items() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    work_insert = sa.text(
        "INSERT INTO action_work_items "
        "(id, enterprise_id, work_key, proposal_id, scope_type, scope_key, status, "
        "assignee_principal_id, assignee_name, owner_role, title, due_hint, kpi, "
        "stop_condition, priority, version, claimed_at, started_at, blocked_at, "
        "completed_at, blocker_reason, result_summary, result_evidence_refs, "
        "created_at, updated_at) VALUES "
        "(:id, :enterprise_id, :work_key, :proposal_id, :scope_type, :scope_key, "
        "'ready', NULL, NULL, :owner_role, :title, :due_hint, :kpi, :stop_condition, "
        ":priority, 1, NULL, NULL, NULL, NULL, NULL, NULL, :evidence_refs, "
        ":created_at, :updated_at)"
    ).bindparams(sa.bindparam("evidence_refs", type_=sa.JSON()))
    event_insert = sa.text(
        "INSERT INTO action_work_events "
        "(id, enterprise_id, work_item_id, actor_principal_id, actor_name, "
        "event_type, from_status, to_status, comment, evidence_refs, "
        "idempotency_key, actor_snapshot, created_at) VALUES "
        "(:id, :enterprise_id, :work_item_id, :actor_principal_id, :actor_name, "
        "'created', NULL, 'ready', :comment, :evidence_refs, :idempotency_key, "
        ":actor_snapshot, :created_at)"
    ).bindparams(
        sa.bindparam("evidence_refs", type_=sa.JSON()),
        sa.bindparam("actor_snapshot", type_=sa.JSON()),
    )
    proposals = connection.execute(
        sa.text(
            "SELECT id, enterprise_id, proposal_key, scope_type, scope_key, owner, title, "
            "due_hint, kpi, stop_condition, parameters, approved_by_actor_key, "
            "approved_by_name, approved_at FROM action_proposals WHERE status = 'approved'"
        )
    ).mappings()
    for proposal in proposals:
        work_id = f"action_work_{uuid4().hex}"
        priority = "normal"
        parameters = proposal["parameters"]
        if isinstance(parameters, str):
            try:
                parameters = json.loads(parameters)
            except json.JSONDecodeError:
                parameters = {}
        if isinstance(parameters, dict):
            priority = str(parameters.get("priority", "normal"))
        created_at = proposal["approved_at"] or now
        connection.execute(
            work_insert,
            {
                "id": work_id,
                "enterprise_id": proposal["enterprise_id"],
                "work_key": f"work-{proposal['proposal_key']}",
                "proposal_id": proposal["id"],
                "scope_type": proposal["scope_type"],
                "scope_key": proposal["scope_key"],
                "owner_role": proposal["owner"],
                "title": proposal["title"],
                "due_hint": proposal["due_hint"],
                "kpi": proposal["kpi"],
                "stop_condition": proposal["stop_condition"],
                "priority": priority,
                "evidence_refs": [],
                "created_at": created_at,
                "updated_at": created_at,
            },
        )
        principal_id = connection.execute(
            sa.text(
                "SELECT id FROM principals WHERE enterprise_id = :enterprise_id "
                "AND principal_key = :principal_key"
            ),
            {
                "enterprise_id": proposal["enterprise_id"],
                "principal_key": proposal["approved_by_actor_key"],
            },
        ).scalar_one_or_none()
        if principal_id is None:
            continue
        connection.execute(
            event_insert,
            {
                "id": f"action_work_event_{uuid4().hex}",
                "enterprise_id": proposal["enterprise_id"],
                "work_item_id": work_id,
                "actor_principal_id": principal_id,
                "actor_name": proposal["approved_by_name"] or principal_id,
                "comment": "由已批准行动提案迁移为内部工作项",
                "evidence_refs": [],
                "idempotency_key": f"work-created:{proposal['proposal_key']}",
                "actor_snapshot": {},
                "created_at": created_at,
            },
        )


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(f"ix_{table}_{column}", table, [column])
