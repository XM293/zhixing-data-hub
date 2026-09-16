"""Add role twin pilot test cases, runs and immutable human reviews."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_role_twin_test_studio"
down_revision: str | None = "0019_role_twin_versioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "role_twin_test_cases",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("target_twin_profile_id", sa.String(64), nullable=False),
        sa.Column("case_key", sa.String(120), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("risk_level", sa.String(32), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_behaviors", sa.JSON(), nullable=False),
        sa.Column("expected_evidence_refs", sa.JSON(), nullable=False),
        sa.Column("created_by_principal_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["target_twin_profile_id"], ["role_twin_profiles.id"]),
        sa.ForeignKeyConstraint(["created_by_principal_id"], ["principals.id"]),
        sa.UniqueConstraint("enterprise_id", "case_key", "version_number"),
    )
    for column in (
        "enterprise_id",
        "target_twin_profile_id",
        "case_key",
        "status",
        "category",
        "risk_level",
        "created_by_principal_id",
        "created_at",
    ):
        op.create_index(f"ix_role_twin_test_cases_{column}", "role_twin_test_cases", [column])

    op.create_table(
        "role_twin_test_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("case_id", sa.String(64), nullable=False),
        sa.Column("twin_profile_id", sa.String(64), nullable=False),
        sa.Column("role_twin_version_id", sa.String(64), nullable=False),
        sa.Column("agent_run_id", sa.String(64), nullable=False, unique=True),
        sa.Column("actor_principal_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("execution_mode", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(120), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["case_id"], ["role_twin_test_cases.id"]),
        sa.ForeignKeyConstraint(["twin_profile_id"], ["role_twin_profiles.id"]),
        sa.ForeignKeyConstraint(["role_twin_version_id"], ["role_twin_versions.id"]),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_principal_id"], ["principals.id"]),
    )
    for column in (
        "enterprise_id",
        "case_id",
        "twin_profile_id",
        "role_twin_version_id",
        "agent_run_id",
        "actor_principal_id",
        "status",
        "execution_mode",
        "created_at",
    ):
        op.create_index(f"ix_role_twin_test_runs_{column}", "role_twin_test_runs", [column])

    op.create_table(
        "role_twin_test_reviews",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("test_run_id", sa.String(64), nullable=False),
        sa.Column("reviewer_principal_id", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("evidence_grounding", sa.Integer(), nullable=False),
        sa.Column("boundary_adherence", sa.Integer(), nullable=False),
        sa.Column("voice_match", sa.Integer(), nullable=False),
        sa.Column("usefulness", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("actor_snapshot", sa.JSON(), nullable=False),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["test_run_id"], ["role_twin_test_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_principal_id"], ["principals.id"]),
    )
    for column in (
        "enterprise_id",
        "test_run_id",
        "reviewer_principal_id",
        "decision",
        "request_id",
        "run_id",
        "created_at",
    ):
        op.create_index(
            f"ix_role_twin_test_reviews_{column}", "role_twin_test_reviews", [column]
        )


def downgrade() -> None:
    op.drop_table("role_twin_test_reviews")
    op.drop_table("role_twin_test_runs")
    op.drop_table("role_twin_test_cases")
