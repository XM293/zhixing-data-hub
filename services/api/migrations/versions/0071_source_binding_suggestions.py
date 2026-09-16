"""Add review-only, evidence-backed source binding suggestions."""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "0071_source_binding_suggestions"
down_revision = "0070_canonical_operational_facts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_bindings") as batch:
        batch.add_column(sa.Column("suggested_business_unit_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("suggestion_reason", sa.String(64), nullable=True))
        batch.add_column(sa.Column(
            "suggestion_evidence", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch.add_column(sa.Column(
            "suggestion_evidence_count", sa.Integer(), nullable=False, server_default="0"))
        batch.create_foreign_key(
            "fk_source_bindings_suggested_business_unit_id", "business_units",
            ["suggested_business_unit_id"], ["id"])
        batch.create_index("ix_source_bindings_suggested_business_unit_id",
                           ["suggested_business_unit_id"])


def downgrade() -> None:
    with op.batch_alter_table("source_bindings") as batch:
        batch.drop_index("ix_source_bindings_suggested_business_unit_id")
        batch.drop_constraint("fk_source_bindings_suggested_business_unit_id", type_="foreignkey")
        batch.drop_column("suggestion_evidence_count")
        batch.drop_column("suggestion_evidence")
        batch.drop_column("suggestion_reason")
        batch.drop_column("suggested_business_unit_id")
