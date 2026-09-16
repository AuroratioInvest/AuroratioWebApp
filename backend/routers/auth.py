import os
import random
import secrets
from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from starlette.requests import Request as StarletteRequest

import schemas
from core.limiter import limiter
from core.features import legacy_customer_app_enabled, require_legacy_customer_app
from database import get_db
from dependencies import create_access_token, get_active_user, get_current_user
from models import MembershipLevel, TradingProvider, User
from services.email_service import send_email_verification_code, send_password_reset_email
from services.fa_service import (
    disable_user_trading,
    get_or_create_fa_authorization,
    get_or_create_module_positions,
    get_or_create_user_bot_state,
)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_verification_codes: dict[str, dict[str, object]] = {}
_verified_emails: set[str] = set()

_phone_verification_codes: dict[str, dict[str, object]] = {}
_verified_phones: set[str] = set()

_password_reset_tokens: dict[str, dict[str, object]] = {}

CODE_TTL_MINUTES = int(os.getenv("EMAIL_CODE_TTL_MINUTES", "15"))
PHONE_CODE_TTL_MINUTES = int(os.getenv("PHONE_CODE_TTL_MINUTES", "15"))
RESET_TOKEN_TTL_MINUTES = int(os.getenv("RESET_TOKEN_TTL_MINUTES", "30"))

DEV_EMAIL_CODE = os.getenv("DEV_EMAIL_CODE", "123456")
DEV_PHONE_CODE = os.getenv("DEV_PHONE_CODE", "123456")


def _is_production() -> bool:
    return os.getenv("ENV", "development") == "production"


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _normalize_phone(phone: str) -> str:
    return phone.strip().replace(" ", "")


def _generate_code(dev_code: str) -> str:
    if not _is_production():
        return dev_code

    return f"{random.randint(0, 999999):06d}"


def _build_auth_response(user: User) -> schemas.AuthResponse:
    return schemas.AuthResponse(
        access_token=create_access_token(user.id),
        token_type="bearer",
        user=user,
    )


@router.post(
    "/send-verification",
    dependencies=[Depends(require_legacy_customer_app)],
)
@limiter.limit("5/minute")
async def send_verification(
    request: StarletteRequest,
    body: schemas.EmailVerificationRequest,
    db: Session = Depends(get_db),
):
    email = _normalize_email(body.email)

    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    code = _generate_code(DEV_EMAIL_CODE)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)

    _verification_codes[email] = {
        "code": code,
        "expires_at": expires_at,
    }

    sent = await send_email_verification_code(email, code)

    if not sent:
        print(f"AuroRatio email verification code for {email}: {code}")

    return {"status": "sent"}


@router.post(
    "/verify-email",
    dependencies=[Depends(require_legacy_customer_app)],
)
@limiter.limit("10/minute")
def verify_email(
    request: StarletteRequest,
    body: schemas.VerifyEmailRequest,
):
    email = _normalize_email(body.email)
    submitted_code = body.code.strip()

    record = _verification_codes.get(email)
    if not record:
        raise HTTPException(
            status_code=400,
            detail="No verification code was requested for this email",
        )

    expires_at = record["expires_at"]
    if isinstance(expires_at, datetime) and datetime.now(timezone.utc) > expires_at:
        _verification_codes.pop(email, None)
        raise HTTPException(status_code=400, detail="Verification code expired")

    if submitted_code != record["code"]:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    _verified_emails.add(email)
    _verification_codes.pop(email, None)

    return {"status": "verified"}


@router.post(
    "/send-phone-verification",
    dependencies=[Depends(require_legacy_customer_app)],
)
@limiter.limit("5/minute")
def send_phone_verification(
    request: StarletteRequest,
    body: schemas.PhoneVerificationRequest,
):
    phone = _normalize_phone(body.phone)

    if not phone:
        raise HTTPException(status_code=400, detail="Phone number is required")

    code = _generate_code(DEV_PHONE_CODE)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=PHONE_CODE_TTL_MINUTES)

    _phone_verification_codes[phone] = {
        "code": code,
        "expires_at": expires_at,
    }

    print(f"AuroRatio phone verification code for {phone}: {code}")

    return {"status": "sent"}


@router.post(
    "/verify-phone",
    dependencies=[Depends(require_legacy_customer_app)],
)
@limiter.limit("10/minute")
def verify_phone(
    request: StarletteRequest,
    body: schemas.VerifyPhoneRequest,
):
    phone = _normalize_phone(body.phone)
    submitted_code = body.code.strip()

    record = _phone_verification_codes.get(phone)
    if not record:
        raise HTTPException(
            status_code=400,
            detail="No verification code was requested for this phone number",
        )

    expires_at = record["expires_at"]
    if isinstance(expires_at, datetime) and datetime.now(timezone.utc) > expires_at:
        _phone_verification_codes.pop(phone, None)
        raise HTTPException(status_code=400, detail="Verification code expired")

    if submitted_code != record["code"]:
        raise HTTPException(status_code=400, detail="Invalid verification code")

    _verified_phones.add(phone)
    _phone_verification_codes.pop(phone, None)

    return {"status": "verified"}


@router.post(
    "/signup",
    response_model=schemas.AuthResponse,
    dependencies=[Depends(require_legacy_customer_app)],
)
@limiter.limit("5/minute")
def signup(
    request: StarletteRequest,
    body: schemas.SignupRequest,
    db: Session = Depends(get_db),
):
    email = _normalize_email(body.email)
    phone = _normalize_phone(body.phone) if getattr(body, "phone", None) else None

    user = db.query(User).filter(User.email == email).first()
    if user is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    if _is_production() and email not in _verified_emails:
        raise HTTPException(
            status_code=400,
            detail="Email must be verified before signup",
        )

    if _is_production() and phone and phone not in _verified_phones:
        raise HTTPException(
            status_code=400,
            detail="Phone number must be verified before signup",
        )

    hashed_password = pwd_context.hash(body.password)

    new_user = User(
        email=email,
        hashed_password=hashed_password,
        trading_enabled=False,
        preferred_trading_provider=TradingProvider.disabled,
    )

    if hasattr(new_user, "first_name") and getattr(body, "first_name", None):
        new_user.first_name = body.first_name.strip()

    if hasattr(new_user, "last_name") and getattr(body, "last_name", None):
        new_user.last_name = body.last_name.strip()

    if hasattr(new_user, "birthdate") and getattr(body, "birthdate", None):
        new_user.birthdate = body.birthdate

    if hasattr(new_user, "phone") and phone:
        new_user.phone = phone

    if hasattr(new_user, "email_verified"):
        new_user.email_verified = True

    if hasattr(new_user, "phone_verified"):
        new_user.phone_verified = bool(phone)

    db.add(new_user)
    db.flush()

    # Prepare FA-ready state immediately, but keep execution disabled.
    get_or_create_user_bot_state(db, new_user)
    get_or_create_module_positions(db, new_user)
    get_or_create_fa_authorization(db, new_user)
    disable_user_trading(db, new_user)

    db.commit()
    db.refresh(new_user)

    _verified_emails.discard(email)
    if phone:
        _verified_phones.discard(phone)

    return _build_auth_response(new_user)


@router.post("/login", response_model=schemas.TokenResponse)
@limiter.limit("10/minute")
def login(
    request: StarletteRequest,
    body: schemas.LoginRequest,
    db: Session = Depends(get_db),
):
    email = _normalize_email(body.email)

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not pwd_context.verify(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if (
        not legacy_customer_app_enabled()
        and user.membership_level != MembershipLevel.aurum
    ):
        raise HTTPException(status_code=404, detail="Not found")

    return schemas.TokenResponse(
        access_token=create_access_token(user.id),
        token_type="bearer",
    )


@router.post(
    "/forgot-password",
    dependencies=[Depends(require_legacy_customer_app)],
)
@limiter.limit("5/minute")
async def forgot_password(
    request: StarletteRequest,
    body: schemas.ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    email = _normalize_email(body.email)
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return {"status": "sent"}

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

    _password_reset_tokens[token] = {
        "email": email,
        "expires_at": expires_at,
    }

    reset_url = f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/reset-password?token={token}"

    sent = await send_password_reset_email(email, reset_url)

    if not sent:
        print(f"AuroRatio password reset link for {email}: {reset_url}")

    return {"status": "sent"}


@router.post(
    "/reset-password",
    dependencies=[Depends(require_legacy_customer_app)],
)
@limiter.limit("5/minute")
def reset_password(
    request: StarletteRequest,
    body: schemas.ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    token = body.token.strip()
    record = _password_reset_tokens.get(token)

    if not record:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    expires_at = record["expires_at"]
    if isinstance(expires_at, datetime) and datetime.now(timezone.utc) > expires_at:
        _password_reset_tokens.pop(token, None)
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    email = record["email"]
    user = db.query(User).filter(User.email == email).first()

    if not user:
        _password_reset_tokens.pop(token, None)
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    if len(body.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters",
        )

    user.hashed_password = pwd_context.hash(body.password)
    db.commit()

    _password_reset_tokens.pop(token, None)

    return {"status": "updated"}


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    if (
        not legacy_customer_app_enabled()
        and current_user.membership_level != MembershipLevel.aurum
    ):
        raise HTTPException(status_code=404, detail="Not found")
    return current_user


@router.get("/admin/users", response_model=List[schemas.UserResponse])
def get_all_users(
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if current_user.membership_level.value != "aurum":
        raise HTTPException(status_code=403, detail="Admin access required")

    return db.query(User).order_by(User.created_at.desc()).all()


@router.patch("/admin/users/{user_id}/toggle-active")
def toggle_user_active(
    user_id: str,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
):
    if current_user.membership_level.value != "aurum":
        raise HTTPException(status_code=403, detail="Admin access required")

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = not user.is_active

    # If account is deactivated, execution must stop immediately.
    if not user.is_active:
        disable_user_trading(db, user)

    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "is_active": user.is_active,
        "trading_enabled": user.trading_enabled,
    }
