"""Add session identifiers and refresh token hashes for JWT authentication."""

from alembic import op
import sqlalchemy as sa

revision = "9218a312ab40"
down_revision = "415bcb3c659e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("login_sessions", sa.Column("id", sa.Uuid(), nullable=True))
    op.execute("UPDATE login_sessions SET id = gen_random_uuid()")
    op.alter_column("login_sessions", "id", nullable=False)
    op.drop_constraint("login_sessions_pkey", "login_sessions", type_="primary")
    op.alter_column("login_sessions", "token_hash", new_column_name="refresh_token_hash")
    op.create_primary_key("login_sessions_pkey", "login_sessions", ["id"])
    op.create_unique_constraint("login_sessions_refresh_token_hash_key", "login_sessions", ["refresh_token_hash"])


def downgrade() -> None:
    op.drop_constraint("login_sessions_refresh_token_hash_key", "login_sessions", type_="unique")
    op.drop_constraint("login_sessions_pkey", "login_sessions", type_="primary")
    op.alter_column("login_sessions", "refresh_token_hash", new_column_name="token_hash")
    op.create_primary_key("login_sessions_pkey", "login_sessions", ["token_hash"])
    op.drop_column("login_sessions", "id")
