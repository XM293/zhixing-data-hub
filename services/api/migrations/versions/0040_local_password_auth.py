"""Add optional local password hashes for the replaceable auth provider."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_local_password_auth"
down_revision: str | None = "0039_auth_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user_accounts") as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(256), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user_accounts") as batch_op:
        batch_op.drop_column("password_hash")
