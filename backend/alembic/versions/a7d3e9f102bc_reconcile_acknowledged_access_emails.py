"""Keep acknowledged access emails out of the retry queue.

Revision ID: a7d3e9f102bc
Revises: 6f8a2c4d9e10

Reuse delivered_at, the existing persistent provider-acceptance timestamp.
Never infer successful delivery from a paid subscription or a send attempt.
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7d3e9f102bc'
down_revision = '6f8a2c4d9e10'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        UPDATE subscriber_access_fulfillments
        SET status = 'delivered', next_attempt_at = NULL,
            delivery_claimed_at = NULL, processing_claim_id = NULL,
            failed_at = NULL, last_error_code = NULL
        WHERE delivered_at IS NOT NULL
    """))


def downgrade():
    # Delivery acknowledgements must survive rollback; re-queuing them sends
    # customers another invitation. This migration changes no schema.
    pass
