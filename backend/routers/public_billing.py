"""Public accountless Checkout and billing-management endpoints."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4
import logging

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy.orm import Session

from core.limiter import limiter
from database import get_db
from services.public_billing_service import (
    DEFAULT_MONTHLY_PLAN_CODE,
    GENERIC_PORTAL_REQUEST_MESSAGE,
    InvalidPublicBillingRequest,
    PortalTokenRejected,
    PublicBillingConfigurationError,
    PublicBillingProviderError,
    create_public_checkout_session,
    deliver_portal_access_batch,
    exchange_portal_access_token,
    request_portal_access,
)

router = APIRouter()

logger = logging.getLogger(__name__)


class CheckoutSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_code: str = Field(
        default=DEFAULT_MONTHLY_PLAN_CODE,
        min_length=1,
        max_length=100,
    )
    locale: Literal["en", "fr"] = "en"
    request_id: UUID = Field(default_factory=uuid4)


class CheckoutSessionResponse(BaseModel):
    url: str


class PortalLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    locale: Literal["en", "fr"] = "en"


class PortalLinkResponse(BaseModel):
    message: str


class PortalSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=32, max_length=256)


class PortalSessionResponse(BaseModel):
    url: str


@router.post(
    "/checkout-session",
    response_model=CheckoutSessionResponse,
)
@limiter.limit("10/minute")
def create_checkout_session(
    request: Request,
    body: CheckoutSessionRequest = Body(default_factory=CheckoutSessionRequest),
    db: Session = Depends(get_db),
):
    # No cookie-backed customer authentication is used, so this endpoint has no
    # ambient customer authority for CSRF to exploit. Price and redirects remain
    # server-selected, and the public endpoint is rate limited.
    del request
    try:
        checkout_url = create_public_checkout_session(
            db,
            plan_code=body.plan_code,
            locale=body.locale,
            request_id=str(body.request_id),
            now=datetime.now(timezone.utc),
        )
    except InvalidPublicBillingRequest:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The requested subscription plan is unavailable.",
        )
    except PublicBillingConfigurationError:
        logger.exception("Public checkout session creation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure checkout is temporarily unavailable.",
        )
    except PublicBillingProviderError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Secure checkout is temporarily unavailable.",
        )
    return CheckoutSessionResponse(url=checkout_url)


@router.post(
    "/portal-link",
    response_model=PortalLinkResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("5/minute")
async def create_portal_link(
    request: Request,
    body: PortalLinkRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    del request
    try:
        delivery_batch = await request_portal_access(
            db,
            email=str(body.email),
            locale=body.locale,
            now=datetime.now(timezone.utc),
        )
        if delivery_batch is not None:
            background_tasks.add_task(
                deliver_portal_access_batch,
                delivery_batch,
            )
    except (PublicBillingConfigurationError, PublicBillingProviderError):
        # The public response remains identical so provider/configuration
        # failures cannot reveal whether a subscriber exists.
        pass
    return PortalLinkResponse(message=GENERIC_PORTAL_REQUEST_MESSAGE)


@router.post(
    "/portal-session",
    response_model=PortalSessionResponse,
)
@limiter.limit("10/minute")
def create_portal_session(
    request: Request,
    body: PortalSessionRequest,
    db: Session = Depends(get_db),
):
    del request
    try:
        portal_url = exchange_portal_access_token(
            db,
            raw_token=body.token,
            now=datetime.now(timezone.utc),
        )
    except PortalTokenRejected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This billing-management link is invalid or expired.",
        )
    except PublicBillingConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secure billing management is temporarily unavailable.",
        )
    except PublicBillingProviderError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Secure billing management is temporarily unavailable.",
        )
    return PortalSessionResponse(url=portal_url)
