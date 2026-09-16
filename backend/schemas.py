from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birthdate: Optional[str] = None
    phone: Optional[str] = None
    email_verified: Optional[bool] = False
    phone_verified: Optional[bool] = False

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class EmailVerificationRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str


class PhoneVerificationRequest(BaseModel):
    phone: str


class VerifyPhoneRequest(BaseModel):
    phone: str
    code: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class ContactRequest(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    description: str
    phone: Optional[str] = None


class TokenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    access_token: str
    token_type: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    email: str
    membership_level: str
    is_active: bool
    trading_enabled: bool = False
    preferred_trading_provider: str = "disabled"
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class RatiosResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    AU_AG: float
    AU_PT: float
    AU_PD: float
    date: datetime


class BotStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    m1_position: str
    m1_silver_days: int
    m2_position: str
    m2_platinum_days: int
    m3_position: str
    m3_palladium_days: int
    last_updated: Optional[datetime] = None
    last_cycle_run: Optional[datetime] = None


class UserBotStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    user_id: str
    trading_enabled: bool

    m1_enabled: bool
    m1_position: str
    m1_silver_days: int
    m1_status: str
    m1_error_message: Optional[str] = None
    m1_retry_count: int
    m1_last_trade_at: Optional[datetime] = None

    m2_enabled: bool
    m2_position: str
    m2_platinum_days: int
    m2_status: str
    m2_error_message: Optional[str] = None
    m2_retry_count: int
    m2_last_trade_at: Optional[datetime] = None

    m3_enabled: bool
    m3_position: str
    m3_palladium_days: int
    m3_status: str
    m3_error_message: Optional[str] = None
    m3_retry_count: int
    m3_last_trade_at: Optional[datetime] = None

    last_updated: Optional[datetime] = None


class UserTradingControlsUpdate(BaseModel):
    trading_enabled: Optional[bool] = None
    preferred_trading_provider: Optional[str] = None

    m1_enabled: Optional[bool] = None
    m2_enabled: Optional[bool] = None
    m3_enabled: Optional[bool] = None


class PortfolioSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: datetime
    value_chf: float
    metal_held: str
    gold_oz_equiv: float


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    metal: str
    etf_symbol: str
    quantity: float
    last_price_gbp: Optional[float] = None
    value_chf: Optional[float] = None
    last_synced_at: Optional[datetime] = None


class SignalLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date: datetime
    au_ag: float
    au_pt: float
    au_pd: float
    signal_fired: bool
    signal_target: Optional[str] = None


class FAAuthorizationCreate(BaseModel):
    user_id: str
    advisor_master_account_id: Optional[str] = None
    ibkr_client_account_id: Optional[str] = None
    authorization_reference: Optional[str] = None
    notes: Optional[str] = None


class FAAuthorizationUpdate(BaseModel):
    status: Optional[str] = None
    advisor_master_account_id: Optional[str] = None
    ibkr_client_account_id: Optional[str] = None
    authorization_reference: Optional[str] = None
    notes: Optional[str] = None


class FAAuthorizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    user_id: str
    status: str
    advisor_master_account_id: Optional[str] = None
    ibkr_client_account_id: Optional[str] = None
    authorization_reference: Optional[str] = None
    notes: Optional[str] = None
    requested_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    suspended_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class IBKRAccountMappingCreate(BaseModel):
    user_id: str
    advisor_master_account_id: str
    ibkr_client_account_id: str
    account_alias: Optional[str] = None
    base_currency: str = "CHF"
    is_active: bool = True
    trading_enabled: bool = True


class IBKRAccountMappingUpdate(BaseModel):
    advisor_master_account_id: Optional[str] = None
    ibkr_client_account_id: Optional[str] = None
    account_alias: Optional[str] = None
    base_currency: Optional[str] = None
    is_active: Optional[bool] = None
    trading_enabled: Optional[bool] = None


class IBKRAccountMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    advisor_master_account_id: str
    ibkr_client_account_id: str
    account_alias: Optional[str] = None
    base_currency: str
    is_active: bool
    trading_enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class UserModulePositionCreate(BaseModel):
    user_id: str
    module_name: str
    metal: str = "GOLD"
    etf_symbol: str = "SGLN"
    quantity: float = 0.0
    last_value_chf: float = 0.0
    is_enabled: bool = True


class UserModulePositionUpdate(BaseModel):
    metal: Optional[str] = None
    etf_symbol: Optional[str] = None
    quantity: Optional[float] = None
    last_value_chf: Optional[float] = None
    last_fill_price: Optional[float] = None
    is_enabled: Optional[bool] = None


class UserModulePositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    module_name: str
    metal: str
    etf_symbol: str
    quantity: float
    last_value_chf: float
    last_fill_price: Optional[float] = None
    last_sell_order_id: Optional[str] = None
    last_buy_order_id: Optional[str] = None
    last_execution_log_id: Optional[str] = None
    is_enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExecutionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    user_id: str
    idempotency_key: Optional[str] = None
    provider: str
    module_name: str
    from_metal: Optional[str] = None
    to_metal: Optional[str] = None
    ratio_col: Optional[str] = None
    ratio_value: Optional[float] = None
    target_value_chf: Optional[float] = None
    estimated_value_chf: Optional[float] = None
    from_quantity: Optional[float] = None
    to_quantity: Optional[float] = None
    units: Optional[float] = None
    sell_order_id: Optional[str] = None
    buy_order_id: Optional[str] = None
    order_id: Optional[str] = None
    dry_run: bool
    status: str
    error_message: Optional[str] = None
    raw_response: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None