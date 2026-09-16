"""Add server-side authentication sessions for replaceable providers."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0039_auth_sessions"
down_revision: str | None = "0038_identity_catalog_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("enterprise_id", sa.String(64), nullable=False),
        sa.Column("user_account_id", sa.String(64), nullable=False),
        sa.Column("session_token_hash", sa.String(128), nullable=False),
        sa.Column("authentication_method", sa.String(48), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_id", sa.String(96), nullable=False),
        sa.Column("run_id", sa.String(96), nullable=False),
        sa.ForeignKeyConstraint(["enterprise_id"], ["enterprises.id"]),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_accounts.id"]),
        sa.UniqueConstraint("session_token_hash"),
    )
    for column in ("enterprise_id", "user_account_id", "session_token_hash", "expires_at"):
        op.create_index(f"ix_auth_sessions_{column}", "auth_sessions", [column])


def downgrade() -> None:
    op.drop_table("auth_sessions")
