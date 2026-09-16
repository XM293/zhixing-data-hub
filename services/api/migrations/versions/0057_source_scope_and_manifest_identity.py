"""Bind sources to projects and scope Raw manifest identity to a run/page."""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0057_source_scope_and_manifest_identity"
down_revision: str | None = "0056_currency_and_source_time"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "business_unit_id" not in {c["name"] for c in inspector.get_columns("external_systems")}:
        op.add_column(
            "external_systems", sa.Column("business_unit_id", sa.String(64), nullable=True)
        )
        if bind.dialect.name != "sqlite":
            op.create_foreign_key(
                "fk_external_systems_business_unit",
                "external_systems",
                "business_units",
                ["business_unit_id"],
                ["id"],
            )
    # A content hash identifies an immutable blob, not a manifest occurrence.
    constraints = sa.inspect(bind).get_unique_constraints("raw_page_manifests")
    for item in constraints:
        if item.get("column_names") == ["content_hash"]:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table(
                    "raw_page_manifests",
                    recreate="always",
                    naming_convention={"uq": "uq_%(table_name)s_%(column_0_name)s"},
                ) as batch:
                    batch.drop_constraint(
                        item["name"] or "uq_raw_page_manifests_content_hash", type_="unique"
                    )
            else:
                op.drop_constraint(item["name"], "raw_page_manifests", type_="unique")
            break
    if not any(
        i.get("name") == "ix_raw_page_manifests_content_hash"
        for i in sa.inspect(bind).get_indexes("raw_page_manifests")
    ):
        op.create_index(
            "ix_raw_page_manifests_content_hash", "raw_page_manifests", ["content_hash"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_index("ix_raw_page_manifests_content_hash", table_name="raw_page_manifests")
        op.create_unique_constraint(
            "uq_raw_page_manifests_content_hash", "raw_page_manifests", ["content_hash"]
        )
        op.drop_constraint(
            "fk_external_systems_business_unit", "external_systems", type_="foreignkey"
        )
    else:
        indexes = sa.inspect(bind).get_indexes("raw_page_manifests")
        if any(i.get("name") == "ix_raw_page_manifests_content_hash" for i in indexes):
            op.drop_index("ix_raw_page_manifests_content_hash", table_name="raw_page_manifests")
        with op.batch_alter_table("raw_page_manifests", recreate="always") as batch:
            batch.create_unique_constraint("uq_raw_page_manifests_content_hash", ["content_hash"])
    op.drop_column("external_systems", "business_unit_id")
