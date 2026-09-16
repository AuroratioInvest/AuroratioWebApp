"""add access fulfillments

Revision ID: f4a7b8c9d012
Revises: d2a7f6c9b104
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a7b8c9d012"
down_revision: Union[str, Sequence[str], None] = "d2a7f6c9b104"
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
    with op.batch_alter_table("plan_channel_mappings") as batch_op:
        batch_op.create_unique_constraint(
            "uq_plan_channel_mapping_identity",
            ["id", "plan_id", "channel_id"],
        )
    op.create_table(
        "subscriber_access_fulfillments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("subscriber_id", sa.String(), nullable=False),
        sa.Column("subscriber_subscription_id", sa.String(), nullable=False),
        sa.Column("access_entitlement_id", sa.String(), nullable=False),
        sa.Column("subscription_plan_id", sa.String(), nullable=False),
        sa.Column("telegram_channel_id", sa.String(), nullable=False),
        sa.Column("plan_channel_mapping_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            portable_enum(
                "pending",
                "processing",
                "delivered",
                "retryable_failure",
                "terminal_failure",
                "cancelled",
                name="access_fulfillment_status",
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_invite_reference", sa.String(length=255), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_claim_id", sa.String(length=64), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_access_fulfillment_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "last_error_code IS NULL OR length(trim(last_error_code)) > 0",
            name="ck_access_fulfillment_error_code_nonempty",
        ),
        sa.CheckConstraint(
            "provider_invite_reference IS NULL OR length(trim(provider_invite_reference)) > 0",
            name="ck_access_fulfillment_invite_reference_nonempty",
        ),
        sa.CheckConstraint(
            "processing_claim_id IS NULL OR length(trim(processing_claim_id)) > 0",
            name="ck_access_fulfillment_claim_id_nonempty",
        ),
        sa.CheckConstraint(
            "next_attempt_at IS NULL OR next_attempt_at >= created_at",
            name="ck_access_fulfillment_next_attempt_after_creation",
        ),
        sa.CheckConstraint(
            "last_attempt_at IS NULL OR last_attempt_at >= created_at",
            name="ck_access_fulfillment_last_attempt_after_creation",
        ),
        sa.CheckConstraint(
            "delivery_claimed_at IS NULL OR delivery_claimed_at >= created_at",
            name="ck_access_fulfillment_claimed_after_creation",
        ),
        sa.CheckConstraint(
            "delivered_at IS NULL OR delivered_at >= created_at",
            name="ck_access_fulfillment_delivered_after_creation",
        ),
        sa.CheckConstraint(
            "failed_at IS NULL OR failed_at >= created_at",
            name="ck_access_fulfillment_failed_after_creation",
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_id"],
            ["subscribers.id"],
        ),
        sa.ForeignKeyConstraint(
            ["subscription_plan_id"],
            ["subscription_plans.id"],
        ),
        sa.ForeignKeyConstraint(
            ["telegram_channel_id"],
            ["telegram_channels.id"],
        ),
        sa.ForeignKeyConstraint(
            ["plan_channel_mapping_id"],
            ["plan_channel_mappings.id"],
        ),
        sa.ForeignKeyConstraint(
            [
                "plan_channel_mapping_id",
                "subscription_plan_id",
                "telegram_channel_id",
            ],
            [
                "plan_channel_mappings.id",
                "plan_channel_mappings.plan_id",
                "plan_channel_mappings.channel_id",
            ],
            name="fk_access_fulfillment_mapping_identity",
        ),
        sa.ForeignKeyConstraint(
            ["access_entitlement_id", "subscriber_id", "subscriber_subscription_id"],
            [
                "access_entitlements.id",
                "access_entitlements.subscriber_id",
                "access_entitlements.subscriber_subscription_id",
            ],
            name="fk_access_fulfillment_entitlement_identity",
        ),
        sa.ForeignKeyConstraint(
            [
                "subscriber_subscription_id",
                "subscriber_id",
                "subscription_plan_id",
            ],
            [
                "subscriber_subscriptions.id",
                "subscriber_subscriptions.subscriber_id",
                "subscriber_subscriptions.plan_id",
            ],
            name="fk_access_fulfillment_subscription_identity",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "access_entitlement_id",
            "plan_channel_mapping_id",
            name="uq_access_fulfillment_entitlement_mapping",
        ),
    )
    op.create_index(
        "ix_subscriber_access_fulfillments_access_entitlement_id",
        "subscriber_access_fulfillments",
        ["access_entitlement_id"],
    )
    op.create_index(
        "ix_subscriber_access_fulfillments_plan_channel_mapping_id",
        "subscriber_access_fulfillments",
        ["plan_channel_mapping_id"],
    )
    op.create_index(
        "ix_subscriber_access_fulfillments_subscriber_id",
        "subscriber_access_fulfillments",
        ["subscriber_id"],
    )
    op.create_index(
        "ix_subscriber_access_fulfillments_subscriber_subscription_id",
        "subscriber_access_fulfillments",
        ["subscriber_subscription_id"],
    )
    op.create_index(
        "ix_subscriber_access_fulfillments_subscription_plan_id",
        "subscriber_access_fulfillments",
        ["subscription_plan_id"],
    )
    op.create_index(
        "ix_subscriber_access_fulfillments_telegram_channel_id",
        "subscriber_access_fulfillments",
        ["telegram_channel_id"],
    )
    op.create_index(
        "ix_subscriber_access_fulfillments_status",
        "subscriber_access_fulfillments",
        ["status"],
    )
    op.create_index(
        "ix_subscriber_access_fulfillments_next_attempt_at",
        "subscriber_access_fulfillments",
        ["next_attempt_at"],
    )
    op.create_index(
        "ix_access_fulfillments_due",
        "subscriber_access_fulfillments",
        ["status", "next_attempt_at", "delivery_claimed_at"],
    )
    op.create_index(
        "ix_access_fulfillments_admin_status",
        "subscriber_access_fulfillments",
        ["status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_access_fulfillments_admin_status",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_index(
        "ix_access_fulfillments_due",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_index(
        "ix_subscriber_access_fulfillments_next_attempt_at",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_index(
        "ix_subscriber_access_fulfillments_status",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_index(
        "ix_subscriber_access_fulfillments_telegram_channel_id",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_index(
        "ix_subscriber_access_fulfillments_subscription_plan_id",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_index(
        "ix_subscriber_access_fulfillments_subscriber_subscription_id",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_index(
        "ix_subscriber_access_fulfillments_subscriber_id",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_index(
        "ix_subscriber_access_fulfillments_plan_channel_mapping_id",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_index(
        "ix_subscriber_access_fulfillments_access_entitlement_id",
        table_name="subscriber_access_fulfillments",
    )
    op.drop_table("subscriber_access_fulfillments")
    with op.batch_alter_table("plan_channel_mappings") as batch_op:
        batch_op.drop_constraint(
            "uq_plan_channel_mapping_identity",
            type_="unique",
        )
