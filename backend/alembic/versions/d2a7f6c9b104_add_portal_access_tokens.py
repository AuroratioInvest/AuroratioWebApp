"""add portal access tokens and issuance cooldowns

Revision ID: d2a7f6c9b104
Revises: 8c4f2a1d9b73
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2a7f6c9b104"
down_revision: Union[str, Sequence[str], None] = "8c4f2a1d9b73"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def portable_enum(*values: str, name: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    op.create_table(
        "portal_access_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("subscriber_id", sa.String(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=False),
        sa.Column(
            "purpose",
            portable_enum(
                "customer_portal",
                name="portal_access_token_purpose",
            ),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(token_hash)) = 64",
            name="ck_portal_access_token_hash_length",
        ),
        sa.CheckConstraint(
            "length(trim(stripe_customer_id)) > 0",
            name="ck_portal_access_token_stripe_customer_id_nonempty",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_portal_access_token_expiry_after_creation",
        ),
        sa.CheckConstraint(
            "delivery_claimed_at IS NULL OR delivery_claimed_at >= created_at",
            name="ck_portal_access_token_delivery_claimed_after_creation",
        ),
        sa.CheckConstraint(
            "delivered_at IS NULL OR delivered_at >= created_at",
            name="ck_portal_access_token_delivered_after_creation",
        ),
        sa.CheckConstraint(
            "delivery_failed_at IS NULL OR delivery_failed_at >= created_at",
            name="ck_portal_access_token_delivery_failed_after_creation",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name="ck_portal_access_token_consumed_after_creation",
        ),
        sa.CheckConstraint(
            "invalidated_at IS NULL OR invalidated_at >= created_at",
            name="ck_portal_access_token_invalidated_after_creation",
        ),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_portal_access_tokens_token_hash",
        ),
    )
    op.create_index(
        "ix_portal_access_tokens_correlation_id",
        "portal_access_tokens",
        ["correlation_id"],
    )
    op.create_index(
        "ix_portal_access_tokens_purpose_expires",
        "portal_access_tokens",
        ["purpose", "expires_at"],
    )
    op.create_index(
        "ix_portal_access_tokens_subscriber_id",
        "portal_access_tokens",
        ["subscriber_id"],
    )
    op.create_index(
        "ix_portal_access_tokens_customer_purpose_expires",
        "portal_access_tokens",
        ["stripe_customer_id", "purpose", "expires_at"],
    )
    op.create_table(
        "portal_link_issuances",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("subscriber_id", sa.String(), nullable=False),
        sa.Column("last_issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "next_allowed_at > last_issued_at",
            name="ck_portal_link_issuance_cooldown",
        ),
        sa.CheckConstraint(
            "last_issued_at >= created_at",
            name="ck_portal_link_issuance_after_creation",
        ),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscriber_id",
            name="uq_portal_link_issuances_subscriber",
        ),
    )
    op.create_index(
        "ix_portal_link_issuances_next_allowed_at",
        "portal_link_issuances",
        ["next_allowed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_portal_link_issuances_next_allowed_at",
        table_name="portal_link_issuances",
    )
    op.drop_table("portal_link_issuances")
    op.drop_index(
        "ix_portal_access_tokens_subscriber_id",
        table_name="portal_access_tokens",
    )
    op.drop_index(
        "ix_portal_access_tokens_customer_purpose_expires",
        table_name="portal_access_tokens",
    )
    op.drop_index(
        "ix_portal_access_tokens_purpose_expires",
        table_name="portal_access_tokens",
    )
    op.drop_index(
        "ix_portal_access_tokens_correlation_id",
        table_name="portal_access_tokens",
    )
    op.drop_table("portal_access_tokens")
