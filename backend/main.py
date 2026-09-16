from pathlib import Path
from datetime import datetime, timezone
import logging

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from core.limiter import limiter
from core.public_urls import PublicAppUrlConfigurationError, public_app_origin
from database import SessionLocal
from routers import (
    admin_fulfillment,
    admin_private_channel_operations,
    admin_signal_publications,
    contact,
    market,
    public_billing,
    stripe_router,
)
from services import telegram_updates
from services.public_billing_service import (
    PublicBillingConfigurationError,
    ensure_public_monthly_plan_configured,
)
from services.private_channel_bootstrap_service import (
    PrivateChannelBootstrapConfigurationError,
    ensure_private_channel_configured,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AuroRatio API",
    version="2.1.0",
    swagger_ui_parameters={"persistAuthorization": True},
)

allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]

try:
    configured_public_origin = public_app_origin(required=False)
except PublicAppUrlConfigurationError:
    configured_public_origin = None

if configured_public_origin and configured_public_origin not in allowed_origins:
    allowed_origins.append(configured_public_origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.on_event("startup")
def startup():
    import models  # noqa: F401 — ensures all models are registered

    db = SessionLocal()

    try:
        now = datetime.now(timezone.utc)

        ensure_public_monthly_plan_configured(
            db,
            now=now,
        )

        ensure_private_channel_configured(
            db,
            now=now,
        )

    except PublicBillingConfigurationError:
        db.rollback()
        logger.info(
            "Public billing plan bootstrap skipped; "
            "Stripe plan config is incomplete"
        )

    except PrivateChannelBootstrapConfigurationError as exc:
        db.rollback()
        logger.info(
            "Private channel bootstrap skipped: %s",
            exc,
        )

    finally:
        db.close()


@app.on_event("shutdown")
def shutdown():
    return None


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Stripe webhook
# ---------------------------------------------------------------------------

stripe_webhook_router = APIRouter()

stripe_webhook_router.add_api_route(
    "/webhook",
    stripe_router.stripe_webhook,
    methods=["POST"],
)

app.include_router(
    stripe_webhook_router,
    prefix="/stripe",
    tags=["stripe"],
)


# ---------------------------------------------------------------------------
# Telegram webhook
# ---------------------------------------------------------------------------

app.include_router(
    telegram_updates.router,
)


# ---------------------------------------------------------------------------
# Administrative subscriber operations
# ---------------------------------------------------------------------------

app.include_router(
    admin_fulfillment.router,
)

app.include_router(
    admin_private_channel_operations.router,
)

app.include_router(
    admin_signal_publications.signal_router,
)

app.include_router(
    admin_signal_publications.publication_router,
)


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

app.include_router(
    contact.router,
    prefix="/contact",
    tags=["contact"],
)

app.include_router(
    market.router,
    prefix="/market",
    tags=["market"],
)

app.include_router(
    public_billing.router,
    prefix="/public/billing",
    tags=["public-billing"],
)
