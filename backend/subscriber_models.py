"""Accountless subscription-domain persistence models.

These models intentionally do not depend on the legacy ``User`` model. The only
foreign keys to ``users`` attribute privileged administrative actions.
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from database import Base


def utc_now():
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Persist aware datetimes in UTC and restore SQLite values as aware UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("UTCDateTime requires a timezone-aware datetime")
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def enum_column(enum_type: type[enum.Enum], name: str) -> SAEnum:
    """Use portable string-backed enums with database CHECK constraints."""
    return SAEnum(
        enum_type,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class SubscriberBillingStatus(enum.Enum):
    pending = "pending"
    active = "active"
    delinquent = "delinquent"
    cancelled = "cancelled"
    ended = "ended"


class EntitlementAccessStatus(enum.Enum):
    pending = "pending"
    active = "active"
    grace_period = "grace_period"
    expired = "expired"
    revoked = "revoked"
    suspended = "suspended"


class IntegrationProvider(enum.Enum):
    stripe = "stripe"
    telegram = "telegram"
    email = "email"


class IntegrationProcessingStatus(enum.Enum):
    received = "received"
    processing = "processing"
    processed = "processed"
    retryable_failure = "retryable_failure"
    permanently_failed = "permanently_failed"
    ignored = "ignored"


class SubscriptionEventSource(enum.Enum):
    stripe = "stripe"
    admin = "admin"
    system = "system"


class AuditActorType(enum.Enum):
    admin = "admin"
    system = "system"
    integration = "integration"


class PortalAccessTokenPurpose(enum.Enum):
    customer_portal = "customer_portal"


class AccessFulfillmentStatus(enum.Enum):
    pending = "pending"
    processing = "processing"
    delivered = "delivered"
    retryable_failure = "retryable_failure"
    terminal_failure = "terminal_failure"
    cancelled = "cancelled"


class TelegramMembershipStatus(enum.Enum):
    active = "active"
    removal_pending = "removal_pending"
    processing = "processing"
    retryable_failure = "retryable_failure"
    removed = "removed"
    terminal_failure = "terminal_failure"


class SubscriberSignalStatus(enum.Enum):
    draft = "draft"
    approved = "approved"
    cancelled = "cancelled"


class SubscriberSignalDirection(enum.Enum):
    buy = "buy"
    sell = "sell"


class SignalPublicationStatus(enum.Enum):
    pending = "pending"
    processing = "processing"
    published = "published"
    retryable_failure = "retryable_failure"
    terminal_failure = "terminal_failure"
    cancelled = "cancelled"


class SignalDeliveryAttemptOutcome(enum.Enum):
    processing = "processing"
    delivered = "delivered"
    transient_failure = "transient_failure"
    permanent_failure = "permanent_failure"
    abandoned = "abandoned"


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(100), nullable=False, unique=True)
    display_name_en = Column(String(255), nullable=False)
    display_name_fr = Column(String(255), nullable=False)
    stripe_price_id = Column(String(255), unique=True)
    billing_interval = Column(String(50))
    is_active = Column(Boolean, nullable=False, default=False)
    is_configured = Column(Boolean, nullable=False, default=False)
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    archived_at = Column(UTCDateTime())

    subscriptions = relationship("SubscriberSubscription", back_populates="plan")
    channel_mappings = relationship("PlanChannelMapping", back_populates="plan")

    __table_args__ = (
        CheckConstraint(
            "length(trim(code)) > 0",
            name="ck_subscription_plan_code_nonempty",
        ),
        CheckConstraint(
            "stripe_price_id IS NULL OR length(trim(stripe_price_id)) > 0",
            name="ck_subscription_plan_stripe_price_id_nonempty",
        ),
    )


class TelegramChannel(Base):
    __tablename__ = "telegram_channels"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(100), nullable=False, unique=True)
    telegram_chat_id = Column(BigInteger, unique=True)
    display_name_en = Column(String(255), nullable=False)
    display_name_fr = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=False)
    is_configured = Column(Boolean, nullable=False, default=False)
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    archived_at = Column(UTCDateTime())

    plan_mappings = relationship("PlanChannelMapping", back_populates="channel")

    __table_args__ = (
        CheckConstraint(
            "length(trim(code)) > 0",
            name="ck_telegram_channel_code_nonempty",
        ),
    )


class PlanChannelMapping(Base):
    __tablename__ = "plan_channel_mappings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    plan_id = Column(
        String,
        ForeignKey("subscription_plans.id"),
        nullable=False,
        index=True,
    )
    channel_id = Column(
        String,
        ForeignKey("telegram_channels.id"),
        nullable=False,
        index=True,
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    plan = relationship("SubscriptionPlan", back_populates="channel_mappings")
    channel = relationship("TelegramChannel", back_populates="plan_mappings")

    __table_args__ = (
        UniqueConstraint("plan_id", "channel_id", name="uq_plan_channel_mapping"),
        UniqueConstraint(
            "id",
            "plan_id",
            "channel_id",
            name="uq_plan_channel_mapping_identity",
        ),
    )


class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    stripe_customer_id = Column(String(255), nullable=False, unique=True)
    stripe_email = Column(String(320))
    normalized_email = Column(String(320), index=True)
    preferred_language = Column(String(20))
    billing_country = Column(String(2))
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    archived_at = Column(UTCDateTime())

    subscriptions = relationship("SubscriberSubscription", back_populates="subscriber")
    portal_access_tokens = relationship(
        "PortalAccessToken",
        back_populates="subscriber",
    )
    portal_link_issuance = relationship(
        "PortalLinkIssuance",
        back_populates="subscriber",
        uselist=False,
    )
    entitlements = relationship(
        "AccessEntitlement",
        back_populates="subscriber",
        viewonly=True,
    )

    __table_args__ = (
        CheckConstraint(
            "billing_country IS NULL OR length(billing_country) = 2",
            name="ck_subscriber_billing_country_length",
        ),
        CheckConstraint(
            "length(trim(stripe_customer_id)) > 0",
            name="ck_subscriber_stripe_customer_id_nonempty",
        ),
        CheckConstraint(
            "normalized_email IS NULL OR length(trim(normalized_email)) > 0",
            name="ck_subscriber_normalized_email_nonempty",
        ),
    )


class SubscriberSubscription(Base):
    __tablename__ = "subscriber_subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_id = Column(
        String,
        ForeignKey("subscribers.id"),
        nullable=False,
        index=True,
    )
    plan_id = Column(
        String,
        ForeignKey("subscription_plans.id"),
        nullable=False,
        index=True,
    )
    stripe_subscription_id = Column(String(255), nullable=False, unique=True)
    stripe_status = Column(String(100))
    billing_status = Column(
        enum_column(SubscriberBillingStatus, "subscriber_billing_status"),
        nullable=False,
        default=SubscriberBillingStatus.pending,
        index=True,
    )
    current_period_start = Column(UTCDateTime())
    current_period_end = Column(UTCDateTime())
    cancel_at_period_end = Column(Boolean, nullable=False, default=False)
    cancelled_at = Column(UTCDateTime())
    ended_at = Column(UTCDateTime())
    latest_provider_event_created_at = Column(UTCDateTime())
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    archived_at = Column(UTCDateTime())

    subscriber = relationship("Subscriber", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    entitlements = relationship("AccessEntitlement", back_populates="subscription")

    __table_args__ = (
        UniqueConstraint(
            "id",
            "subscriber_id",
            name="uq_subscriber_subscription_owner",
        ),
        UniqueConstraint(
            "id",
            "subscriber_id",
            "plan_id",
            name="uq_subscriber_subscription_identity",
        ),
        CheckConstraint(
            "length(trim(stripe_subscription_id)) > 0",
            name="ck_subscriber_subscription_stripe_id_nonempty",
        ),
    )


class AccessEntitlement(Base):
    __tablename__ = "access_entitlements"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_id = Column(
        String,
        ForeignKey("subscribers.id"),
        nullable=False,
        index=True,
    )
    subscriber_subscription_id = Column(
        String,
        nullable=False,
    )
    plan_id = Column(
        String,
        ForeignKey("subscription_plans.id"),
        nullable=False,
        index=True,
    )
    status = Column(
        enum_column(EntitlementAccessStatus, "entitlement_access_status"),
        nullable=False,
        default=EntitlementAccessStatus.pending,
    )
    access_starts_at = Column(UTCDateTime())
    paid_through_at = Column(UTCDateTime())
    grace_period_ends_at = Column(UTCDateTime())
    administratively_revoked = Column(Boolean, nullable=False, default=False)
    revocation_reason = Column(Text)
    revoked_by_admin_user_id = Column(String)
    revoked_at = Column(UTCDateTime())
    expires_at = Column(UTCDateTime())
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    subscriber = relationship(
        "Subscriber",
        back_populates="entitlements",
        viewonly=True,
    )
    subscription = relationship(
        "SubscriberSubscription",
        back_populates="entitlements",
    )
    plan = relationship("SubscriptionPlan", viewonly=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["subscriber_subscription_id", "subscriber_id", "plan_id"],
            [
                "subscriber_subscriptions.id",
                "subscriber_subscriptions.subscriber_id",
                "subscriber_subscriptions.plan_id",
            ],
            name="fk_access_entitlement_subscription_identity",
        ),
        UniqueConstraint(
            "subscriber_subscription_id",
            name="uq_access_entitlement_subscription",
        ),
        UniqueConstraint(
            "id",
            "subscriber_id",
            "subscriber_subscription_id",
            name="uq_access_entitlement_event_identity",
        ),
        Index(
            "ix_access_entitlements_status_paid_through",
            "status",
            "paid_through_at",
        ),
        Index(
            "ix_access_entitlements_status_grace_deadline",
            "status",
            "grace_period_ends_at",
        ),
    )


class SubscriptionAccessEvent(Base):
    __tablename__ = "subscription_access_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_id = Column(
        String,
        ForeignKey("subscribers.id"),
        nullable=False,
        index=True,
    )
    subscriber_subscription_id = Column(
        String,
        index=True,
    )
    entitlement_id = Column(String, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    previous_billing_status = Column(String(100))
    new_billing_status = Column(String(100))
    previous_access_status = Column(String(100))
    new_access_status = Column(String(100))
    reason = Column(Text)
    source = Column(
        enum_column(SubscriptionEventSource, "subscription_event_source"),
        nullable=False,
    )
    external_event_id = Column(String(255))
    event_metadata = Column("metadata", JSON)
    occurred_at = Column(UTCDateTime(), nullable=False)
    recorded_at = Column(UTCDateTime(), nullable=False, default=utc_now)

    __table_args__ = (
        ForeignKeyConstraint(
            ["subscriber_subscription_id", "subscriber_id"],
            [
                "subscriber_subscriptions.id",
                "subscriber_subscriptions.subscriber_id",
            ],
            name="fk_access_event_subscription_owner",
        ),
        ForeignKeyConstraint(
            ["entitlement_id", "subscriber_id", "subscriber_subscription_id"],
            [
                "access_entitlements.id",
                "access_entitlements.subscriber_id",
                "access_entitlements.subscriber_subscription_id",
            ],
            name="fk_access_event_entitlement_identity",
        ),
        CheckConstraint(
            "entitlement_id IS NULL OR subscriber_subscription_id IS NOT NULL",
            name="ck_access_event_entitlement_requires_subscription",
        ),
    )


class IntegrationEvent(Base):
    __tablename__ = "integration_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    provider = Column(
        enum_column(IntegrationProvider, "integration_provider"),
        nullable=False,
    )
    external_event_id = Column(String(255), nullable=False)
    event_type = Column(String(255), nullable=False)
    provider_created_at = Column(UTCDateTime())
    received_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    processing_status = Column(
        enum_column(
            IntegrationProcessingStatus,
            "integration_processing_status",
        ),
        nullable=False,
        default=IntegrationProcessingStatus.received,
    )
    processing_attempts = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(UTCDateTime())
    processed_at = Column(UTCDateTime())
    last_error = Column(Text)
    payload_checksum = Column(String(64))
    selected_metadata = Column(JSON)
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "external_event_id",
            name="uq_integration_provider_external_event",
        ),
        CheckConstraint(
            "processing_attempts >= 0",
            name="ck_integration_event_attempts_nonnegative",
        ),
        CheckConstraint(
            "length(trim(external_event_id)) > 0",
            name="ck_integration_event_external_id_nonempty",
        ),
        Index(
            "ix_integration_events_processing_retry",
            "processing_status",
            "next_retry_at",
        ),
    )


class PortalAccessToken(Base):
    """Hashed, purpose-bound, single-use access to Stripe billing management."""

    __tablename__ = "portal_access_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash = Column(String(64), nullable=False, unique=True)
    subscriber_id = Column(
        String,
        ForeignKey("subscribers.id"),
        nullable=False,
        index=True,
    )
    stripe_customer_id = Column(String(255), nullable=False)
    purpose = Column(
        enum_column(PortalAccessTokenPurpose, "portal_access_token_purpose"),
        nullable=False,
        default=PortalAccessTokenPurpose.customer_portal,
    )
    expires_at = Column(UTCDateTime(), nullable=False)
    delivery_claimed_at = Column(UTCDateTime())
    delivered_at = Column(UTCDateTime())
    delivery_failed_at = Column(UTCDateTime())
    consumed_at = Column(UTCDateTime())
    invalidated_at = Column(UTCDateTime())
    correlation_id = Column(String(255), index=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    subscriber = relationship("Subscriber", back_populates="portal_access_tokens")

    __table_args__ = (
        CheckConstraint(
            "length(trim(token_hash)) = 64",
            name="ck_portal_access_token_hash_length",
        ),
        CheckConstraint(
            "length(trim(stripe_customer_id)) > 0",
            name="ck_portal_access_token_stripe_customer_id_nonempty",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_portal_access_token_expiry_after_creation",
        ),
        CheckConstraint(
            "delivery_claimed_at IS NULL OR delivery_claimed_at >= created_at",
            name="ck_portal_access_token_delivery_claimed_after_creation",
        ),
        CheckConstraint(
            "delivered_at IS NULL OR delivered_at >= created_at",
            name="ck_portal_access_token_delivered_after_creation",
        ),
        CheckConstraint(
            "delivery_failed_at IS NULL OR delivery_failed_at >= created_at",
            name="ck_portal_access_token_delivery_failed_after_creation",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name="ck_portal_access_token_consumed_after_creation",
        ),
        CheckConstraint(
            "invalidated_at IS NULL OR invalidated_at >= created_at",
            name="ck_portal_access_token_invalidated_after_creation",
        ),
        Index(
            "ix_portal_access_tokens_purpose_expires",
            "purpose",
            "expires_at",
        ),
        Index(
            "ix_portal_access_tokens_customer_purpose_expires",
            "stripe_customer_id",
            "purpose",
            "expires_at",
        ),
    )


class PortalLinkIssuance(Base):
    """Cross-instance cooldown state for one Stripe Customer relationship."""

    __tablename__ = "portal_link_issuances"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_id = Column(
        String,
        ForeignKey("subscribers.id"),
        nullable=False,
    )
    last_issued_at = Column(UTCDateTime(), nullable=False)
    next_allowed_at = Column(UTCDateTime(), nullable=False, index=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    subscriber = relationship("Subscriber", back_populates="portal_link_issuance")

    __table_args__ = (
        UniqueConstraint(
            "subscriber_id",
            name="uq_portal_link_issuances_subscriber",
        ),
        CheckConstraint(
            "next_allowed_at > last_issued_at",
            name="ck_portal_link_issuance_cooldown",
        ),
        CheckConstraint(
            "last_issued_at >= created_at",
            name="ck_portal_link_issuance_after_creation",
        ),
    )


class SubscriberAccessFulfillment(Base):
    """Durable private-channel access fulfillment for one entitlement/channel."""

    __tablename__ = "subscriber_access_fulfillments"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_id = Column(
        String,
        ForeignKey("subscribers.id"),
        nullable=False,
        index=True,
    )
    subscriber_subscription_id = Column(String, nullable=False, index=True)
    access_entitlement_id = Column(String, nullable=False, index=True)
    subscription_plan_id = Column(
        String,
        ForeignKey("subscription_plans.id"),
        nullable=False,
        index=True,
    )
    telegram_channel_id = Column(
        String,
        ForeignKey("telegram_channels.id"),
        nullable=False,
        index=True,
    )
    plan_channel_mapping_id = Column(
        String,
        ForeignKey("plan_channel_mappings.id"),
        nullable=False,
        index=True,
    )
    status = Column(
        enum_column(AccessFulfillmentStatus, "access_fulfillment_status"),
        nullable=False,
        default=AccessFulfillmentStatus.pending,
        index=True,
    )
    attempt_count = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(UTCDateTime())
    next_attempt_at = Column(UTCDateTime(), index=True)
    last_attempt_at = Column(UTCDateTime())
    provider_invite_reference = Column(String(255))
    invite_expires_at = Column(UTCDateTime())
    delivery_claimed_at = Column(UTCDateTime())
    processing_claim_id = Column(String(64))
    delivered_at = Column(UTCDateTime())
    failed_at = Column(UTCDateTime())
    last_error_code = Column(String(100))
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    subscriber = relationship("Subscriber", viewonly=True)
    entitlement = relationship("AccessEntitlement", viewonly=True)
    subscription = relationship("SubscriberSubscription", viewonly=True)
    plan = relationship("SubscriptionPlan", viewonly=True)
    channel = relationship("TelegramChannel", viewonly=True)
    plan_channel_mapping = relationship(
        "PlanChannelMapping",
        primaryjoin=(
            "and_("
            "SubscriberAccessFulfillment.plan_channel_mapping_id == PlanChannelMapping.id, "
            "SubscriberAccessFulfillment.subscription_plan_id == PlanChannelMapping.plan_id, "
            "SubscriberAccessFulfillment.telegram_channel_id == PlanChannelMapping.channel_id"
            ")"
        ),
        foreign_keys=(
            "[SubscriberAccessFulfillment.plan_channel_mapping_id, "
            "SubscriberAccessFulfillment.subscription_plan_id, "
            "SubscriberAccessFulfillment.telegram_channel_id]"
        ),
        viewonly=True,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["access_entitlement_id", "subscriber_id", "subscriber_subscription_id"],
            [
                "access_entitlements.id",
                "access_entitlements.subscriber_id",
                "access_entitlements.subscriber_subscription_id",
            ],
            name="fk_access_fulfillment_entitlement_identity",
        ),
        ForeignKeyConstraint(
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
        ForeignKeyConstraint(
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
        UniqueConstraint(
            "access_entitlement_id",
            "plan_channel_mapping_id",
            name="uq_access_fulfillment_entitlement_mapping",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_access_fulfillment_attempts_nonnegative",
        ),
        CheckConstraint(
            "last_error_code IS NULL OR length(trim(last_error_code)) > 0",
            name="ck_access_fulfillment_error_code_nonempty",
        ),
        CheckConstraint(
            "provider_invite_reference IS NULL OR length(trim(provider_invite_reference)) > 0",
            name="ck_access_fulfillment_invite_reference_nonempty",
        ),
        CheckConstraint(
            "processing_claim_id IS NULL OR length(trim(processing_claim_id)) > 0",
            name="ck_access_fulfillment_claim_id_nonempty",
        ),
        CheckConstraint(
            "next_attempt_at IS NULL OR next_attempt_at >= created_at",
            name="ck_access_fulfillment_next_attempt_after_creation",
        ),
        CheckConstraint(
            "last_attempt_at IS NULL OR last_attempt_at >= created_at",
            name="ck_access_fulfillment_last_attempt_after_creation",
        ),
        CheckConstraint(
            "delivery_claimed_at IS NULL OR delivery_claimed_at >= created_at",
            name="ck_access_fulfillment_claimed_after_creation",
        ),
        CheckConstraint(
            "delivered_at IS NULL OR delivered_at >= created_at",
            name="ck_access_fulfillment_delivered_after_creation",
        ),
        CheckConstraint(
            "failed_at IS NULL OR failed_at >= created_at",
            name="ck_access_fulfillment_failed_after_creation",
        ),
        Index(
            "ix_access_fulfillments_due",
            "status",
            "next_attempt_at",
            "delivery_claimed_at",
        ),
        Index(
            "ix_access_fulfillments_admin_status",
            "status",
            "updated_at",
        ),
    )


class SubscriberSignal(Base):
    """Canonical admin-approved signal content for accountless subscribers."""

    __tablename__ = "subscriber_signals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    status = Column(
        enum_column(SubscriberSignalStatus, "subscriber_signal_status"),
        nullable=False,
        default=SubscriberSignalStatus.draft,
        index=True,
    )
    symbol = Column(String(100), nullable=False)
    direction = Column(
        enum_column(SubscriberSignalDirection, "subscriber_signal_direction"),
        nullable=False,
    )
    entry = Column(Text, nullable=False)
    stop_loss = Column(Text, nullable=False)
    take_profit_targets = Column(JSON, nullable=False)
    analysis = Column(Text)
    expires_at = Column(UTCDateTime())
    strategy_identifier = Column(String(100))
    strategy_version = Column(String(100))
    strategy_ratio_identifier = Column(String(50))
    strategy_decision_date = Column(String(10))
    strategy_decision_type = Column(String(100))
    strategy_identity = Column(String(255), unique=True)
    created_by_admin_user_id = Column(String)
    approved_by_admin_user_id = Column(String)
    cancelled_by_admin_user_id = Column(String)
    approved_at = Column(UTCDateTime())
    cancelled_at = Column(UTCDateTime())
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    plan_targets = relationship(
        "SubscriberSignalPlanTarget",
        back_populates="signal",
    )
    publications = relationship(
        "SubscriberSignalPublication",
        back_populates="signal",
    )

    __table_args__ = (
        CheckConstraint(
            "length(trim(symbol)) > 0",
            name="ck_subscriber_signal_symbol_nonempty",
        ),
        CheckConstraint(
            "length(trim(entry)) > 0",
            name="ck_subscriber_signal_entry_nonempty",
        ),
        CheckConstraint(
            "length(trim(stop_loss)) > 0",
            name="ck_subscriber_signal_stop_loss_nonempty",
        ),
        CheckConstraint(
            "approved_at IS NULL OR approved_at >= created_at",
            name="ck_subscriber_signal_approved_after_creation",
        ),
        CheckConstraint(
            "cancelled_at IS NULL OR cancelled_at >= created_at",
            name="ck_subscriber_signal_cancelled_after_creation",
        ),
        CheckConstraint(
            "strategy_identity IS NULL OR length(trim(strategy_identity)) > 0",
            name="ck_subscriber_signal_strategy_identity_nonempty",
        ),
        CheckConstraint(
            "strategy_decision_date IS NULL OR length(strategy_decision_date) = 10",
            name="ck_subscriber_signal_strategy_date_length",
        ),
        Index("ix_subscriber_signals_status_created", "status", "created_at"),
        Index(
            "ix_subscriber_signals_strategy_lookup",
            "strategy_identifier",
            "strategy_version",
            "strategy_ratio_identifier",
            "strategy_decision_date",
        ),
    )


class SubscriberSignalPlanTarget(Base):
    """Relational targeting of a subscriber signal to a subscription plan."""

    __tablename__ = "subscriber_signal_plan_targets"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    signal_id = Column(
        String,
        ForeignKey("subscriber_signals.id"),
        nullable=False,
        index=True,
    )
    plan_id = Column(
        String,
        ForeignKey("subscription_plans.id"),
        nullable=False,
        index=True,
    )
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)

    signal = relationship("SubscriberSignal", back_populates="plan_targets")
    plan = relationship("SubscriptionPlan", viewonly=True)

    __table_args__ = (
        UniqueConstraint(
            "signal_id",
            "plan_id",
            name="uq_subscriber_signal_plan_target",
        ),
        UniqueConstraint(
            "id",
            "signal_id",
            "plan_id",
            name="uq_subscriber_signal_plan_target_identity",
        ),
    )


class SubscriberSignalPublication(Base):
    """Durable publication work for one signal and one plan/channel mapping."""

    __tablename__ = "subscriber_signal_publications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_signal_id = Column(
        String,
        ForeignKey("subscriber_signals.id"),
        nullable=False,
        index=True,
    )
    signal_plan_target_id = Column(
        String,
        ForeignKey("subscriber_signal_plan_targets.id"),
        nullable=False,
        index=True,
    )
    plan_channel_mapping_id = Column(
        String,
        ForeignKey("plan_channel_mappings.id"),
        nullable=False,
        index=True,
    )
    subscription_plan_id = Column(
        String,
        ForeignKey("subscription_plans.id"),
        nullable=False,
        index=True,
    )
    telegram_channel_id = Column(
        String,
        ForeignKey("telegram_channels.id"),
        nullable=False,
        index=True,
    )
    status = Column(
        enum_column(SignalPublicationStatus, "signal_publication_status"),
        nullable=False,
        default=SignalPublicationStatus.pending,
        index=True,
    )
    attempt_count = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(UTCDateTime())
    next_attempt_at = Column(UTCDateTime(), index=True)
    processing_started_at = Column(UTCDateTime())
    processing_claim_id = Column(String(64))
    provider_message_reference = Column(String(255))
    telegram_chat_id = Column(BigInteger)
    telegram_message_id = Column(BigInteger)
    published_at = Column(UTCDateTime())
    failed_at = Column(UTCDateTime())
    cancelled_at = Column(UTCDateTime())
    last_error_code = Column(String(100))
    last_error_message = Column(String(500))
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    signal = relationship("SubscriberSignal", back_populates="publications")
    signal_plan_target = relationship(
        "SubscriberSignalPlanTarget",
        primaryjoin=(
            "and_("
            "SubscriberSignalPublication.signal_plan_target_id == SubscriberSignalPlanTarget.id, "
            "SubscriberSignalPublication.subscriber_signal_id == SubscriberSignalPlanTarget.signal_id, "
            "SubscriberSignalPublication.subscription_plan_id == SubscriberSignalPlanTarget.plan_id"
            ")"
        ),
        foreign_keys=(
            "[SubscriberSignalPublication.signal_plan_target_id, "
            "SubscriberSignalPublication.subscriber_signal_id, "
            "SubscriberSignalPublication.subscription_plan_id]"
        ),
        viewonly=True,
    )
    plan_channel_mapping = relationship(
        "PlanChannelMapping",
        primaryjoin=(
            "and_("
            "SubscriberSignalPublication.plan_channel_mapping_id == PlanChannelMapping.id, "
            "SubscriberSignalPublication.subscription_plan_id == PlanChannelMapping.plan_id, "
            "SubscriberSignalPublication.telegram_channel_id == PlanChannelMapping.channel_id"
            ")"
        ),
        foreign_keys=(
            "[SubscriberSignalPublication.plan_channel_mapping_id, "
            "SubscriberSignalPublication.subscription_plan_id, "
            "SubscriberSignalPublication.telegram_channel_id]"
        ),
        viewonly=True,
    )
    plan = relationship("SubscriptionPlan", viewonly=True)
    channel = relationship("TelegramChannel", viewonly=True)
    delivery_attempts = relationship(
        "SubscriberSignalDeliveryAttempt",
        back_populates="publication",
        order_by="SubscriberSignalDeliveryAttempt.attempt_number",
    )

    __table_args__ = (
        ForeignKeyConstraint(
            [
                "signal_plan_target_id",
                "subscriber_signal_id",
                "subscription_plan_id",
            ],
            [
                "subscriber_signal_plan_targets.id",
                "subscriber_signal_plan_targets.signal_id",
                "subscriber_signal_plan_targets.plan_id",
            ],
            name="fk_signal_publication_target_identity",
        ),
        ForeignKeyConstraint(
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
            name="fk_signal_publication_mapping_identity",
        ),
        UniqueConstraint(
            "subscriber_signal_id",
            "plan_channel_mapping_id",
            name="uq_signal_publication_signal_mapping",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_signal_publication_attempts_nonnegative",
        ),
        CheckConstraint(
            "processing_claim_id IS NULL OR length(trim(processing_claim_id)) > 0",
            name="ck_signal_publication_claim_id_nonempty",
        ),
        CheckConstraint(
            "provider_message_reference IS NULL OR length(trim(provider_message_reference)) > 0",
            name="ck_signal_publication_message_reference_nonempty",
        ),
        CheckConstraint(
            "last_error_code IS NULL OR length(trim(last_error_code)) > 0",
            name="ck_signal_publication_error_code_nonempty",
        ),
        CheckConstraint(
            "last_error_message IS NULL OR length(trim(last_error_message)) > 0",
            name="ck_signal_publication_error_message_nonempty",
        ),
        CheckConstraint(
            "last_attempt_at IS NULL OR last_attempt_at >= created_at",
            name="ck_signal_publication_last_attempt_after_creation",
        ),
        CheckConstraint(
            "next_attempt_at IS NULL OR next_attempt_at >= created_at",
            name="ck_signal_publication_next_attempt_after_creation",
        ),
        CheckConstraint(
            "processing_started_at IS NULL OR processing_started_at >= created_at",
            name="ck_signal_publication_processing_after_creation",
        ),
        CheckConstraint(
            "published_at IS NULL OR published_at >= created_at",
            name="ck_signal_publication_published_after_creation",
        ),
        CheckConstraint(
            "failed_at IS NULL OR failed_at >= created_at",
            name="ck_signal_publication_failed_after_creation",
        ),
        CheckConstraint(
            "cancelled_at IS NULL OR cancelled_at >= created_at",
            name="ck_signal_publication_cancelled_after_creation",
        ),
        Index(
            "ix_signal_publications_due",
            "status",
            "next_attempt_at",
            "processing_started_at",
        ),
        Index(
            "ix_signal_publications_admin_status",
            "status",
            "updated_at",
        ),
        Index(
            "ix_signal_publications_signal_status",
            "subscriber_signal_id",
            "status",
        ),
    )


class SubscriberSignalDeliveryAttempt(Base):
    """Immutable history for one actual Telegram delivery attempt."""

    __tablename__ = "subscriber_signal_delivery_attempts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    signal_publication_id = Column(
        String,
        ForeignKey("subscriber_signal_publications.id"),
        nullable=False,
        index=True,
    )
    attempt_number = Column(Integer, nullable=False)
    processing_claim_id = Column(String(64), nullable=False)
    outcome = Column(
        enum_column(SignalDeliveryAttemptOutcome, "signal_delivery_attempt_outcome"),
        nullable=False,
        default=SignalDeliveryAttemptOutcome.processing,
        index=True,
    )
    started_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    completed_at = Column(UTCDateTime())
    telegram_chat_id = Column(BigInteger)
    telegram_message_id = Column(BigInteger)
    provider_message_reference = Column(String(255))
    error_code = Column(String(100))
    error_message = Column(String(500))
    is_retryable = Column(Boolean)
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)

    publication = relationship(
        "SubscriberSignalPublication",
        back_populates="delivery_attempts",
    )

    __table_args__ = (
        UniqueConstraint(
            "signal_publication_id",
            "attempt_number",
            name="uq_signal_delivery_attempt_number",
        ),
        UniqueConstraint(
            "signal_publication_id",
            "processing_claim_id",
            name="uq_signal_delivery_attempt_claim",
        ),
        CheckConstraint(
            "attempt_number > 0",
            name="ck_signal_delivery_attempt_number_positive",
        ),
        CheckConstraint(
            "length(trim(processing_claim_id)) > 0",
            name="ck_signal_delivery_attempt_claim_nonempty",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_signal_delivery_attempt_completed_after_start",
        ),
        CheckConstraint(
            "provider_message_reference IS NULL OR length(trim(provider_message_reference)) > 0",
            name="ck_signal_delivery_attempt_reference_nonempty",
        ),
        CheckConstraint(
            "error_code IS NULL OR length(trim(error_code)) > 0",
            name="ck_signal_delivery_attempt_error_code_nonempty",
        ),
        CheckConstraint(
            "error_message IS NULL OR length(trim(error_message)) > 0",
            name="ck_signal_delivery_attempt_error_message_nonempty",
        ),
        Index(
            "ix_signal_delivery_attempts_publication_started",
            "signal_publication_id",
            "started_at",
        ),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_type = Column(
        enum_column(AuditActorType, "audit_actor_type"),
        nullable=False,
    )
    actor_admin_user_id = Column(String)
    action = Column(String(150), nullable=False, index=True)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(String, nullable=False)
    reason = Column(Text)
    event_metadata = Column("metadata", JSON)
    correlation_id = Column(String(255), index=True)
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)

    __table_args__ = (
        Index("ix_audit_events_entity", "entity_type", "entity_id"),
    )

    
class TelegramMembership(Base):
    """Observed Telegram membership bound to an AuroRatio subscriber invite.

    The binding is created from Telegram ``chat_member`` webhook updates when a
    user joins through a single-use invite generated for a fulfillment record.
    It gives reconciliation workers the numeric Telegram user ID required to
    remove access after all entitlements for the channel have ended.
    """

    __tablename__ = "telegram_memberships"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    subscriber_id = Column(
        String, ForeignKey("subscribers.id"), nullable=False, index=True
    )
    subscriber_subscription_id = Column(
        String, ForeignKey("subscriber_subscriptions.id"), nullable=False, index=True
    )
    access_entitlement_id = Column(
        String, ForeignKey("access_entitlements.id"), nullable=False, index=True
    )
    access_fulfillment_id = Column(
        String,
        ForeignKey("subscriber_access_fulfillments.id"),
        nullable=False,
        index=True,
    )
    telegram_channel_id = Column(
        String, ForeignKey("telegram_channels.id"), nullable=False, index=True
    )
    telegram_chat_id = Column(BigInteger, nullable=False, index=True)
    telegram_user_id = Column(BigInteger, nullable=False, index=True)
    status = Column(
        enum_column(TelegramMembershipStatus, "telegram_membership_status"),
        nullable=False,
        default=TelegramMembershipStatus.active,
        index=True,
    )
    attempt_count = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(UTCDateTime())
    next_attempt_at = Column(UTCDateTime(), index=True)
    processing_started_at = Column(UTCDateTime())
    processing_claim_id = Column(String(64))
    joined_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    removed_at = Column(UTCDateTime())
    last_error_code = Column(String(100))
    last_error_message = Column(Text)
    created_at = Column(UTCDateTime(), nullable=False, default=utc_now)
    updated_at = Column(
        UTCDateTime(), nullable=False, default=utc_now, onupdate=utc_now
    )

    subscriber = relationship("Subscriber", viewonly=True)
    subscription = relationship("SubscriberSubscription", viewonly=True)
    entitlement = relationship("AccessEntitlement", viewonly=True)
    fulfillment = relationship("SubscriberAccessFulfillment", viewonly=True)
    channel = relationship("TelegramChannel", viewonly=True)

    __table_args__ = (
        UniqueConstraint(
            "telegram_channel_id",
            "telegram_user_id",
            name="uq_telegram_membership_channel_user",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_telegram_membership_attempts_nonnegative",
        ),
        Index(
            "ix_telegram_membership_reconciliation",
            "status",
            "next_attempt_at",
        ),
    )