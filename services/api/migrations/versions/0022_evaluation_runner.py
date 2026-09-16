"""Add versioned enterprise AI evaluation suites and runs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_evaluation_runner"
down_revision: str | None = "0021_agent_feedback_and_handoff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "evaluation_suites",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("suite_key", sa.String(120), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(48), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.UniqueConstraint("enterprise_id", "suite_key", "version_number"),
    )
    for column in ("enterprise_id", "suite_key", "domain", "status", "created_at"):
        op.create_index(f"ix_evaluation_suites_{column}", "evaluation_suites", [column])

    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("suite_id", sa.String(64), nullable=False),
        sa.Column("case_key", sa.String(120), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("domain", sa.String(48), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("actor_login_name", sa.String(100), nullable=False),
        sa.Column("target_twin_key", sa.String(100), nullable=False),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("expectations", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("suite_id", "case_key", "version_number"),
    )
    for column in (
        "suite_id", "case_key", "domain", "risk_level", "actor_login_name",
        "target_twin_key", "status", "created_at",
    ):
        op.create_index(f"ix_evaluation_cases_{column}", "evaluation_cases", [column])

    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("suite_id", sa.String(64), nullable=False),
        sa.Column("initiated_by_principal_id", sa.String(64), nullable=False),
        sa.Column("baseline_run_id", sa.String(64), nullable=True),
        sa.Column("client_request_key", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("code_version", sa.String(64), nullable=False),
        sa.Column("config_version", sa.String(64), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("passed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("review_required_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("pass_rate", sa.Float(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["suite_id"], ["evaluation_suites.id"]),
        sa.ForeignKeyConstraint(["initiated_by_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["evaluation_runs.id"]),
        sa.UniqueConstraint("enterprise_id", "client_request_key"),
    )
    for column in (
        "enterprise_id", "suite_id", "initiated_by_principal_id", "baseline_run_id",
        "client_request_key", "status", "started_at", "completed_at",
    ):
        op.create_index(f"ix_evaluation_runs_{column}", "evaluation_runs", [column])

    op.create_table(
        "evaluation_run_items",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("evaluation_run_id", sa.String(64), nullable=False),
        sa.Column("evaluation_case_id", sa.String(64), nullable=False),
        sa.Column("actor_principal_id", sa.String(64), nullable=True),
        sa.Column("agent_run_id", sa.String(64), nullable=True),
        sa.Column("case_key", sa.String(120), nullable=False),
        sa.Column("case_version_number", sa.Integer(), nullable=False),
        sa.Column("case_snapshot", sa.JSON(), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("error_types", sa.JSON(), nullable=False),
        sa.Column("observed_error_code", sa.String(96), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evaluation_case_id"], ["evaluation_cases.id"]),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.UniqueConstraint("evaluation_run_id", "evaluation_case_id"),
    )
    for column in (
        "evaluation_run_id", "evaluation_case_id", "actor_principal_id", "agent_run_id",
        "case_key", "outcome", "observed_error_code", "created_at",
    ):
        op.create_index(f"ix_evaluation_run_items_{column}", "evaluation_run_items", [column])


def downgrade() -> None:
    op.drop_table("evaluation_run_items")
    op.drop_table("evaluation_runs")
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_suites")
