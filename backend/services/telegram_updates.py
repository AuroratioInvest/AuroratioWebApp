"""Authenticated Telegram webhook for membership lifecycle updates."""

from __future__ import annotations

import hmac
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, status

from database import SessionLocal
from services.telegram_membership_service import record_chat_member_update

router = APIRouter(prefix="/telegram", tags=["telegram"])


def _webhook_secret() -> str:
    value = os.getenv("TELEGRAM_WEBHOOK_SECRET_TOKEN", "").strip()
    if not value:
        raise RuntimeError("TELEGRAM_WEBHOOK_SECRET_TOKEN is not configured")
    return value


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    expected = _webhook_secret()
    supplied = x_telegram_bot_api_secret_token or ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid update")

    db = SessionLocal()
    try:
        recorded = record_chat_member_update(
            db,
            update=payload,
            now=datetime.now(timezone.utc),
        )
    finally:
        db.close()

    return {"ok": True, "recorded": recorded}
