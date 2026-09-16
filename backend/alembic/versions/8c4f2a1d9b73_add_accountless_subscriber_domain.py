"""add accountless subscriber domain

Revision ID: 8c4f2a1d9b73
Revises: 29f6de39d824
Create Date: 2026-07-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c4f2a1d9b73"
down_revision: Union[str, Sequence[str], None] = "29f6de39d824"
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
        "subscription_plans",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("display_name_en", sa.String(length=255), nullable=False),
        sa.Column("display_name_fr", sa.String(length=255), nullable=False),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=True),
        sa.Column("billing_interval", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_configured", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(code)) > 0",
            name="ck_subscription_plan_code_nonempty",
        ),
        sa.CheckConstraint(
            "stripe_price_id IS NULL OR length(trim(stripe_price_id)) > 0",
            name="ck_subscription_plan_stripe_price_id_nonempty",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_subscription_plans_code"),
        sa.UniqueConstraint(
            "stripe_price_id",
            name="uq_subscription_plans_stripe_price_id",
        ),
    )
    op.create_table(
        "telegram_channels",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("display_name_en", sa.String(length=255), nullable=False),
        sa.Column("display_name_fr", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_configured", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(code)) > 0",
            name="ck_telegram_channel_code_nonempty",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_telegram_channels_code"),
        sa.UniqueConstraint(
            "telegram_chat_id",
            name="uq_telegram_channels_chat_id",
        ),
    )
    op.create_table(
        "subscribers",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_email", sa.String(length=320), nullable=True),
        sa.Column("normalized_email", sa.String(length=320), nullable=True),
        sa.Column("preferred_language", sa.String(length=20), nullable=True),
        sa.Column("billing_country", sa.String(length=2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "billing_country IS NULL OR length(billing_country) = 2",
            name="ck_subscriber_billing_country_length",
        ),
        sa.CheckConstraint(
            "length(trim(stripe_customer_id)) > 0",
            name="ck_subscriber_stripe_customer_id_nonempty",
        ),
        sa.CheckConstraint(
            "normalized_email IS NULL OR length(trim(normalized_email)) > 0",
            name="ck_subscriber_normalized_email_nonempty",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "stripe_customer_id",
            name="uq_subscribers_stripe_customer_id",
        ),
    )
    op.create_index(
        "ix_subscribers_normalized_email",
        "subscribers",
        ["normalized_email"],
    )
    op.create_table(
        "plan_channel_mappings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column("channel_id", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["telegram_channels.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id",
            "channel_id",
            name="uq_plan_channel_mapping",
        ),
    )
    op.create_index(
        "ix_plan_channel_mappings_channel_id",
        "plan_channel_mappings",
        ["channel_id"],
    )
    op.create_index(
        "ix_plan_channel_mappings_plan_id",
        "plan_channel_mappings",
        ["plan_id"],
    )
    op.create_table(
        "subscriber_subscriptions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("subscriber_id", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_status", sa.String(length=100), nullable=True),
        sa.Column(
            "billing_status",
            portable_enum(
                "pending",
                "active",
                "delinquent",
                "cancelled",
                "ended",
                name="subscriber_billing_status",
            ),
            nullable=False,
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "latest_provider_event_created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.CheckConstraint(
            "length(trim(stripe_subscription_id)) > 0",
            name="ck_subscriber_subscription_stripe_id_nonempty",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "subscriber_id",
            name="uq_subscriber_subscription_owner",
        ),
        sa.UniqueConstraint(
            "id",
            "subscriber_id",
            "plan_id",
            name="uq_subscriber_subscription_identity",
        ),
        sa.UniqueConstraint(
            "stripe_subscription_id",
            name="uq_subscriber_subscriptions_stripe_id",
        ),
    )
    op.create_index(
        "ix_subscriber_subscriptions_billing_status",
        "subscriber_subscriptions",
        ["billing_status"],
    )
    op.create_index(
        "ix_subscriber_subscriptions_plan_id",
        "subscriber_subscriptions",
        ["plan_id"],
    )
    op.create_index(
        "ix_subscriber_subscriptions_subscriber_id",
        "subscriber_subscriptions",
        ["subscriber_id"],
    )
    op.create_table(
        "access_entitlements",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("subscriber_id", sa.String(), nullable=False),
        sa.Column("subscriber_subscription_id", sa.String(), nullable=False),
        sa.Column("plan_id", sa.String(), nullable=False),
        sa.Column(
            "status",
            portable_enum(
                "pending",
                "active",
                "grace_period",
                "expired",
                "revoked",
                "suspended",
                name="entitlement_access_status",
            ),
            nullable=False,
        ),
        sa.Column("access_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_through_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_period_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("administratively_revoked", sa.Boolean(), nullable=False),
        sa.Column("revocation_reason", sa.Text(), nullable=True),
        sa.Column("revoked_by_admin_user_id", sa.String(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["subscription_plans.id"]),
        sa.ForeignKeyConstraint(
            ["revoked_by_admin_user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_subscription_id", "subscriber_id", "plan_id"],
            [
                "subscriber_subscriptions.id",
                "subscriber_subscriptions.subscriber_id",
                "subscriber_subscriptions.plan_id",
            ],
            name="fk_access_entitlement_subscription_identity",
        ),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subscriber_subscription_id",
            name="uq_access_entitlement_subscription",
        ),
        sa.UniqueConstraint(
            "id",
            "subscriber_id",
            "subscriber_subscription_id",
            name="uq_access_entitlement_event_identity",
        ),
    )
    op.create_index(
        "ix_access_entitlements_plan_id",
        "access_entitlements",
        ["plan_id"],
    )
    op.create_index(
        "ix_access_entitlements_status_grace_deadline",
        "access_entitlements",
        ["status", "grace_period_ends_at"],
    )
    op.create_index(
        "ix_access_entitlements_status_paid_through",
        "access_entitlements",
        ["status", "paid_through_at"],
    )
    op.create_index(
        "ix_access_entitlements_subscriber_id",
        "access_entitlements",
        ["subscriber_id"],
    )
    op.create_table(
        "subscription_access_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("subscriber_id", sa.String(), nullable=False),
        sa.Column("subscriber_subscription_id", sa.String(), nullable=True),
        sa.Column("entitlement_id", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("previous_billing_status", sa.String(length=100), nullable=True),
        sa.Column("new_billing_status", sa.String(length=100), nullable=True),
        sa.Column("previous_access_status", sa.String(length=100), nullable=True),
        sa.Column("new_access_status", sa.String(length=100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "source",
            portable_enum(
                "stripe",
                "admin",
                "system",
                name="subscription_event_source",
            ),
            nullable=False,
        ),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entitlement_id IS NULL OR subscriber_subscription_id IS NOT NULL",
            name="ck_access_event_entitlement_requires_subscription",
        ),
        sa.ForeignKeyConstraint(
            ["subscriber_subscription_id", "subscriber_id"],
            [
                "subscriber_subscriptions.id",
                "subscriber_subscriptions.subscriber_id",
            ],
            name="fk_access_event_subscription_owner",
        ),
        sa.ForeignKeyConstraint(
            ["entitlement_id", "subscriber_id", "subscriber_subscription_id"],
            [
                "access_entitlements.id",
                "access_entitlements.subscriber_id",
                "access_entitlements.subscriber_subscription_id",
            ],
            name="fk_access_event_entitlement_identity",
        ),
        sa.ForeignKeyConstraint(["subscriber_id"], ["subscribers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_subscription_access_events_entitlement_id",
        "subscription_access_events",
        ["entitlement_id"],
    )
    op.create_index(
        "ix_subscription_access_events_event_type",
        "subscription_access_events",
        ["event_type"],
    )
    op.create_index(
        "ix_subscription_access_events_subscriber_id",
        "subscription_access_events",
        ["subscriber_id"],
    )
    op.create_index(
        "ix_subscription_access_events_subscriber_subscription_id",
        "subscription_access_events",
        ["subscriber_subscription_id"],
    )
    op.create_table(
        "integration_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "provider",
            portable_enum(
                "stripe",
                "telegram",
                "email",
                name="integration_provider",
            ),
            nullable=False,
        ),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=255), nullable=False),
        sa.Column("provider_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "processing_status",
            portable_enum(
                "received",
                "processing",
                "processed",
                "retryable_failure",
                "permanently_failed",
                "ignored",
                name="integration_processing_status",
            ),
            nullable=False,
        ),
        sa.Column("processing_attempts", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("payload_checksum", sa.String(length=64), nullable=True),
        sa.Column("selected_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "processing_attempts >= 0",
            name="ck_integration_event_attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "length(trim(external_event_id)) > 0",
            name="ck_integration_event_external_id_nonempty",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "external_event_id",
            name="uq_integration_provider_external_event",
        ),
    )
    op.create_index(
        "ix_integration_events_processing_retry",
        "integration_events",
        ["processing_status", "next_retry_at"],
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "actor_type",
            portable_enum(
                "admin",
                "system",
                "integration",
                name="audit_actor_type",
            ),
            nullable=False,
        ),
        sa.Column("actor_admin_user_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(length=150), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_admin_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_events_action",
        "audit_events",
        ["action"],
    )
    op.create_index(
        "ix_audit_events_correlation_id",
        "audit_events",
        ["correlation_id"],
    )
    op.create_index(
        "ix_audit_events_entity",
        "audit_events",
        ["entity_type", "entity_id"],
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("integration_events")
    op.drop_table("subscription_access_events")
    op.drop_table("access_entitlements")
    op.drop_table("subscriber_subscriptions")
    op.drop_table("plan_channel_mappings")
    op.drop_table("subscribers")
    op.drop_table("telegram_channels")
    op.drop_table("subscription_plans")
