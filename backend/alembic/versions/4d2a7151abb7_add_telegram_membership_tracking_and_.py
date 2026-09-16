"""add telegram membership tracking and access removal

Revision ID: 4d2a7151abb7
Revises: e5a9c1d2b340
Create Date: 2026-08-08 22:29:45.971750
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from subscriber_models import UTCDateTime


# revision identifiers, used by Alembic.
revision: str = "4d2a7151abb7"
down_revision: Union[str, Sequence[str], None] = "e5a9c1d2b340"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telegram_memberships",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("subscriber_id", sa.String(), nullable=False),
        sa.Column("subscriber_subscription_id", sa.String(), nullable=False),
        sa.Column("access_entitlement_id", sa.String(), nullable=False),
        sa.Column("access_fulfillment_id", sa.String(), nullable=False),
        sa.Column("telegram_channel_id", sa.String(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "active",
                "removal_pending",
                "processing",
                "retryable_failure",
                "removed",
                "terminal_failure",
                name="telegram_membership_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_attempt_at", UTCDateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", UTCDateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", UTCDateTime(timezone=True), nullable=True),
        sa.Column("processing_claim_id", sa.String(length=64), nullable=True),
        sa.Column("joined_at", UTCDateTime(timezone=True), nullable=False),
        sa.Column("removed_at", UTCDateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", UTCDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", UTCDateTime(timezone=True), nullable=False),

        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_telegram_membership_attempts_nonnegative",
        ),

        sa.ForeignKeyConstraint(
            ["access_entitlement_id"],
            ["access_entitlements.id"],
        ),
        sa.ForeignKeyConstraint(
            ["access_fulfillment_id"],
            ["subscriber_access_fulfillments.id"],
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["subscribers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_subscription_id"],
            ["subscriber_subscriptions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["telegram_channel_id"],
            ["telegram_channels.id"],
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "telegram_channel_id",
            "telegram_user_id",
            name="uq_telegram_membership_channel_user",
        ),
    )

    op.create_index(
        "ix_telegram_membership_reconciliation",
        "telegram_memberships",
        ["status", "next_attempt_at"],
        unique=False,
    )

    op.create_index(
        "ix_telegram_memberships_access_entitlement_id",
        "telegram_memberships",
        ["access_entitlement_id"],
        unique=False,
    )

    op.create_index(
        "ix_telegram_memberships_access_fulfillment_id",
        "telegram_memberships",
        ["access_fulfillment_id"],
        unique=False,
    )

    op.create_index(
        "ix_telegram_memberships_next_attempt_at",
        "telegram_memberships",
        ["next_attempt_at"],
        unique=False,
    )

    op.create_index(
        "ix_telegram_memberships_status",
        "telegram_memberships",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_telegram_memberships_subscriber_id",
        "telegram_memberships",
        ["subscriber_id"],
        unique=False,
    )

    op.create_index(
        "ix_telegram_memberships_subscriber_subscription_id",
        "telegram_memberships",
        ["subscriber_subscription_id"],
        unique=False,
    )

    op.create_index(
        "ix_telegram_memberships_telegram_channel_id",
        "telegram_memberships",
        ["telegram_channel_id"],
        unique=False,
    )

    op.create_index(
        "ix_telegram_memberships_telegram_chat_id",
        "telegram_memberships",
        ["telegram_chat_id"],
        unique=False,
    )

    op.create_index(
        "ix_telegram_memberships_telegram_user_id",
        "telegram_memberships",
        ["telegram_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_memberships_telegram_user_id",
        table_name="telegram_memberships",
    )
    op.drop_index(
        "ix_telegram_memberships_telegram_chat_id",
        table_name="telegram_memberships",
    )
    op.drop_index(
        "ix_telegram_memberships_telegram_channel_id",
        table_name="telegram_memberships",
    )
    op.drop_index(
        "ix_telegram_memberships_subscriber_subscription_id",
        table_name="telegram_memberships",
    )
    op.drop_index(
        "ix_telegram_memberships_subscriber_id",
        table_name="telegram_memberships",
    )
    op.drop_index(
        "ix_telegram_memberships_status",
        table_name="telegram_memberships",
    )
    op.drop_index(
        "ix_telegram_memberships_next_attempt_at",
        table_name="telegram_memberships",
    )
    op.drop_index(
        "ix_telegram_memberships_access_fulfillment_id",
        table_name="telegram_memberships",
    )
    op.drop_index(
        "ix_telegram_memberships_access_entitlement_id",
        table_name="telegram_memberships",
    )
    op.drop_index(
        "ix_telegram_membership_reconciliation",
        table_name="telegram_memberships",
    )

    op.drop_table("telegram_memberships")
