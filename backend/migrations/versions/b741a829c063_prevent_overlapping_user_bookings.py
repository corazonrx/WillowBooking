"""Prevent overlapping confirmed reservations for an account."""

from alembic import op

revision = "b741a829c063"
down_revision = "9218a312ab40"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE bookings
        ADD CONSTRAINT no_overlapping_user_bookings
        EXCLUDE USING gist (
            user_id WITH =,
            daterange(check_in, check_out, '[)') WITH &&
        ) WHERE (status = 'confirmed')
    """)


def downgrade():
    op.drop_constraint("no_overlapping_user_bookings", "bookings")
