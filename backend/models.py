import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def utc_now():
    return datetime.now(timezone.utc)


class MembershipLevel(enum.Enum):
    classic = "classic"
    founder = "founder"
    aurum = "aurum"


class SubscriptionStatus(enum.Enum):
    active = "active"
    pending = "pending"
    past_due = "past_due"
    cancelled = "cancelled"


class TradeStatus(enum.Enum):
    success = "success"
    failed = "failed"
    partial = "partial"


class ConnectionStatus(enum.Enum):
    pending = "pending"
    connecting = "connecting"
    syncing = "syncing"
    active = "active"
    failed = "failed"
    disconnected = "disconnected"


class ModuleStatus(enum.Enum):
    ok = "ok"
    pending_switch = "pending_switch"
    cash_pending_retry = "cash_pending_retry"
    cash_manual_review = "cash_manual_review"
    paused = "paused"


class ExecutionStatus(enum.Enum):
    pending = "pending"
    skipped = "skipped"
    success = "success"
    failed = "failed"


class FAAuthorizationStatus(enum.Enum):
    pending_authorization = "pending_authorization"
    active = "active"
    rejected = "rejected"
    revoked = "revoked"
    suspended = "suspended"


class TradingProvider(enum.Enum):
    disabled = "disabled"
    snaptrade = "snaptrade"
    ibkr_fa = "ibkr_fa"


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    membership_level = Column(SAEnum(MembershipLevel), default=MembershipLevel.classic)
    is_active = Column(Boolean, default=False)
    hashed_password = Column(String, nullable=False, default="")

    first_name = Column(String)
    last_name = Column(String)
    birthdate = Column(String)
    phone = Column(String)

    email_verified = Column(Boolean, default=False)
    phone_verified = Column(Boolean, default=False)

    # Global trading kill switch.
    # This should be turned off when the subscription ends, when the user leaves,
    # or when an admin manually disables trading.
    trading_enabled = Column(Boolean, default=False, nullable=False)

    # SnapTrade remains useful for broker connection / portfolio display.
    # IBKR FA is the future production execution path.
    preferred_trading_provider = Column(
        SAEnum(TradingProvider),
        default=TradingProvider.disabled,
        nullable=False,
    )

    subscription = relationship(
        "Subscription",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    broker_connections = relationship(
        "BrokerConnection",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    trade_logs = relationship(
        "TradeLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    portfolio_snapshots = relationship(
        "PortfolioSnapshot",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    positions = relationship(
        "Position",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    user_bot_state = relationship(
        "UserBotState",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    module_positions = relationship(
        "UserModulePosition",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    execution_logs = relationship(
        "ExecutionLog",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    fa_authorization = relationship(
        "FAAuthorization",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    ibkr_account_mapping = relationship(
        "IBKRAccountMapping",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    stripe_customer_id = Column(String)
    stripe_subscription_id = Column(String)
    status = Column(SAEnum(SubscriptionStatus), default=SubscriptionStatus.pending)
    current_period_end = Column(DateTime)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="subscription")


class BrokerConnection(Base):
    __tablename__ = "broker_connections"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    broker_name = Column(String, nullable=False)

    # SnapTrade fields.
    snaptrade_user_id = Column(String, unique=True, index=True)
    snaptrade_account_id = Column(String)
    snaptrade_user_secret = Column(String)

    # SnapTrade is now treated as connection/read/display by default.
    # Execution should happen through IBKR FA once production is ready.
    can_display_portfolio = Column(Boolean, default=True, nullable=False)
    can_execute_trades = Column(Boolean, default=False, nullable=False)

    status = Column(SAEnum(ConnectionStatus), default=ConnectionStatus.pending)
    is_active = Column(Boolean, default=False)

    connected_at = Column(DateTime, default=utc_now)
    disconnected_at = Column(DateTime)

    user = relationship("User", back_populates="broker_connections")
    positions = relationship(
        "Position",
        back_populates="broker_connection",
        cascade="all, delete-orphan",
    )


class FAAuthorization(Base):
    """
    Tracks the business/operational status of the user's authorization under
    your IBKR Financial Advisor master account.

    This is NOT OAuth-per-retail-user. It represents whether the client account
    is linked/authorized to your FA structure and allowed to be included in
    execution.
    """

    __tablename__ = "fa_authorizations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    status = Column(
        SAEnum(FAAuthorizationStatus),
        default=FAAuthorizationStatus.pending_authorization,
        nullable=False,
        index=True,
    )

    advisor_master_account_id = Column(String)
    ibkr_client_account_id = Column(String, index=True)

    authorization_reference = Column(String)
    notes = Column(Text)

    requested_at = Column(DateTime, default=utc_now)
    activated_at = Column(DateTime)
    rejected_at = Column(DateTime)
    revoked_at = Column(DateTime)
    suspended_at = Column(DateTime)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="fa_authorization")


class IBKRAccountMapping(Base):
    """
    Maps an AuroRatio user to the real IBKR account/sub-account identifiers used
    by the FA execution layer.
    """

    __tablename__ = "ibkr_account_mappings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    advisor_master_account_id = Column(String, nullable=False, index=True)
    ibkr_client_account_id = Column(String, nullable=False, unique=True, index=True)

    account_alias = Column(String)
    base_currency = Column(String, default="CHF", nullable=False)

    is_active = Column(Boolean, default=False, nullable=False)
    trading_enabled = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="ibkr_account_mapping")


class BotState(Base):
    __tablename__ = "bot_state"

    id = Column(Integer, primary_key=True, default=1)

    m1_position = Column(String, default="GOLD")
    m1_silver_days = Column(Integer, default=0)

    m2_position = Column(String, default="GOLD")
    m2_platinum_days = Column(Integer, default=0)

    m3_position = Column(String, default="GOLD")
    m3_palladium_days = Column(Integer, default=0)

    last_updated = Column(DateTime, default=utc_now)
    last_cycle_run = Column(DateTime)


class UserBotState(Base):
    __tablename__ = "user_bot_states"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)

    trading_enabled = Column(Boolean, default=False, nullable=False)

    # Module 1 — Gold ↔ Silver
    m1_enabled = Column(Boolean, default=True, nullable=False)
    m1_position = Column(String, default="GOLD")
    m1_silver_days = Column(Integer, default=0)
    m1_status = Column(SAEnum(ModuleStatus), default=ModuleStatus.ok)
    m1_error_message = Column(String)
    m1_retry_count = Column(Integer, default=0)
    m1_last_attempt_at = Column(DateTime)
    m1_last_status_change = Column(DateTime)
    m1_alert_sent_at = Column(DateTime)
    m1_last_trade_at = Column(DateTime)

    # Module 2 — Gold ↔ Platinum
    m2_enabled = Column(Boolean, default=True, nullable=False)
    m2_position = Column(String, default="GOLD")
    m2_platinum_days = Column(Integer, default=0)
    m2_status = Column(SAEnum(ModuleStatus), default=ModuleStatus.ok)
    m2_error_message = Column(String)
    m2_retry_count = Column(Integer, default=0)
    m2_last_attempt_at = Column(DateTime)
    m2_last_status_change = Column(DateTime)
    m2_alert_sent_at = Column(DateTime)
    m2_last_trade_at = Column(DateTime)

    # Module 3 — Gold ↔ Palladium
    m3_enabled = Column(Boolean, default=True, nullable=False)
    m3_position = Column(String, default="GOLD")
    m3_palladium_days = Column(Integer, default=0)
    m3_status = Column(SAEnum(ModuleStatus), default=ModuleStatus.ok)
    m3_error_message = Column(String)
    m3_retry_count = Column(Integer, default=0)
    m3_last_attempt_at = Column(DateTime)
    m3_last_status_change = Column(DateTime)
    m3_alert_sent_at = Column(DateTime)
    m3_last_trade_at = Column(DateTime)

    created_at = Column(DateTime, default=utc_now)
    last_updated = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="user_bot_state")


class TradeLog(Base):
    __tablename__ = "trade_log"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    date = Column(DateTime, default=utc_now)

    module_name = Column(String)
    provider = Column(SAEnum(TradingProvider), default=TradingProvider.disabled)

    from_metal = Column(String)
    to_metal = Column(String)

    ratio_col = Column(String)
    ratio_value = Column(Float)

    quantity = Column(Float)
    fill_price = Column(Float)

    sell_order_id = Column(String)
    buy_order_id = Column(String)

    status = Column(SAEnum(TradeStatus))
    error_message = Column(String)
    raw_response = Column(Text)

    user = relationship("User", back_populates="trade_logs")


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    # Prevent duplicate execution for the same user/module/signal/day.
    idempotency_key = Column(String, unique=True, index=True)

    provider = Column(SAEnum(TradingProvider), default=TradingProvider.disabled, nullable=False)

    fa_authorization_id = Column(String, ForeignKey("fa_authorizations.id"))
    ibkr_account_mapping_id = Column(String, ForeignKey("ibkr_account_mappings.id"))

    module_name = Column(String, nullable=False)

    from_metal = Column(String)
    to_metal = Column(String)

    ratio_col = Column(String)
    ratio_value = Column(Float)

    target_value_chf = Column(Float)
    estimated_value_chf = Column(Float)

    # The virtual module quantity before/after execution.
    from_quantity = Column(Float)
    to_quantity = Column(Float)

    units = Column(Float)

    sell_order_id = Column(String)
    buy_order_id = Column(String)
    order_id = Column(String)

    dry_run = Column(Boolean, default=True, nullable=False)

    status = Column(SAEnum(ExecutionStatus), default=ExecutionStatus.pending)
    error_message = Column(String)
    raw_response = Column(Text)

    created_at = Column(DateTime, default=utc_now)
    finished_at = Column(DateTime)

    user = relationship("User", back_populates="execution_logs")


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)

    date = Column(DateTime, default=utc_now)

    value_chf = Column(Float)
    metal_held = Column(String)
    gold_oz_equiv = Column(Float)

    user = relationship("User", back_populates="portfolio_snapshots")


class Position(Base):
    __tablename__ = "positions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    broker_connection_id = Column(String, ForeignKey("broker_connections.id"), nullable=False)

    metal = Column(String)
    etf_symbol = Column(String)

    quantity = Column(Float)
    last_price_gbp = Column(Float)
    value_chf = Column(Float)

    last_synced_at = Column(DateTime)

    user = relationship("User", back_populates="positions")
    broker_connection = relationship("BrokerConnection", back_populates="positions")


class SignalLog(Base):
    __tablename__ = "signal_log"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    date = Column(DateTime, default=utc_now)

    au_ag = Column(Float)
    au_pt = Column(Float)
    au_pd = Column(Float)

    silver_days = Column(Integer)
    platinum_days = Column(Integer)
    palladium_days = Column(Integer)

    signal_fired = Column(Boolean, default=False)
    signal_target = Column(String)


class UserModulePosition(Base):
    """
    Virtual sub-portfolio ledger.

    IBKR may show one merged real position, e.g.:
        SGLN = 25 shares

    AuroRatio must internally know:
        module1 = 10 shares SGLN
        module3 = 15 shares SGLN

    This table is what makes independent module switching possible.
    """

    __tablename__ = "user_module_positions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    module_name = Column(String, nullable=False)

    metal = Column(String, nullable=False, default="GOLD")
    etf_symbol = Column(String, nullable=False, default="SGLN")

    quantity = Column(Float, default=0.0, nullable=False)

    last_value_chf = Column(Float, default=0.0, nullable=False)
    last_fill_price = Column(Float)

    last_sell_order_id = Column(String)
    last_buy_order_id = Column(String)
    last_execution_log_id = Column(String)

    is_enabled = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="module_positions")

    __table_args__ = (
        UniqueConstraint("user_id", "module_name", name="uq_user_module_position"),
    )


class DailyBotReport(Base):
    __tablename__ = "daily_bot_reports"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    run_date = Column(DateTime, default=utc_now, index=True)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)

    mode = Column(String)
    triggered_by = Column(String, default="scheduler")

    users_checked = Column(Integer, default=0)
    users_skipped = Column(Integer, default=0)

    signals_detected = Column(Integer, default=0)
    executed = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)

    summary_text = Column(String)
    raw_summary = Column(Text)
    error_message = Column(Text)

    created_at = Column(DateTime, default=utc_now)


# Register and re-export the isolated accountless subscriber domain.
from subscriber_models import (  # noqa: E402,F401
    AccessEntitlement,
    AccessFulfillmentStatus,
    AuditActorType,
    AuditEvent,
    EntitlementAccessStatus,
    IntegrationEvent,
    IntegrationProcessingStatus,
    IntegrationProvider,
    PlanChannelMapping,
    PortalAccessToken,
    PortalAccessTokenPurpose,
    PortalLinkIssuance,
    Subscriber,
    SubscriberAccessFulfillment,
    SubscriberBillingStatus,
    SubscriberSignal,
    SubscriberSignalDirection,
    SubscriberSignalPlanTarget,
    SubscriberSignalDeliveryAttempt,
    SubscriberSignalPublication,
    SubscriberSignalStatus,
    SubscriberSubscription,
    SignalDeliveryAttemptOutcome,
    SignalPublicationStatus,
    SubscriptionAccessEvent,
    SubscriptionEventSource,
    SubscriptionPlan,
    TelegramChannel,
)
