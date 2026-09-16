from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_active_admin
from models import User
from services.subscriber_signal_publication_service import (
    SIGNAL_BACKFILL_DEFAULT_LIMIT,
    SIGNAL_BACKFILL_MAX_LIMIT,
    SIGNAL_PUBLICATION_DEFAULT_LIMIT,
    SIGNAL_PUBLICATION_MAX_LIMIT,
    approve_signal,
    backfill_missing_signal_publications,
    cancel_signal,
    create_signal_draft,
    process_due_signal_publications,
    record_manual_signal_processing_requested,
    retry_signal_publication,
    update_signal_draft,
)
from subscriber_models import (
    SubscriberSignalDeliveryAttempt,
    SignalPublicationStatus,
    SubscriberSignal,
    SubscriberSignalDirection,
    SubscriberSignalPublication,
    SubscriberSignalStatus,
)

signal_router = APIRouter(prefix="/admin/subscriber-signals", tags=["Admin Signals"])
publication_router = APIRouter(
    prefix="/admin/signal-publications",
    tags=["Admin Signal Publications"],
)


class SignalDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=100)
    direction: Literal["buy", "sell"]
    entry: str = Field(min_length=1, max_length=1000)
    stop_loss: str = Field(min_length=1, max_length=1000)
    take_profit_targets: list[str] = Field(min_length=1, max_length=5)
    analysis: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = None
    plan_ids: list[str] = Field(min_length=1, max_length=20)


class SignalDraftUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str | None = Field(default=None, min_length=1, max_length=100)
    direction: Literal["buy", "sell"] | None = None
    entry: str | None = Field(default=None, min_length=1, max_length=1000)
    stop_loss: str | None = Field(default=None, min_length=1, max_length=1000)
    take_profit_targets: list[str] | None = Field(default=None, min_length=1, max_length=5)
    analysis: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = None


class SignalBackfillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str | None = None
    dry_run: bool = True
    limit: int = Field(default=SIGNAL_BACKFILL_DEFAULT_LIMIT, ge=1, le=SIGNAL_BACKFILL_MAX_LIMIT)
    after_signal_id: str | None = None


class ProcessDueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(
        default=SIGNAL_PUBLICATION_DEFAULT_LIMIT,
        ge=1,
        le=SIGNAL_PUBLICATION_MAX_LIMIT,
    )


def _serialize_signal(row: SubscriberSignal) -> dict:
    return {
        "id": row.id,
        "status": row.status.value,
        "symbol": row.symbol,
        "direction": row.direction.value,
        "entry": row.entry,
        "stop_loss": row.stop_loss,
        "take_profit_targets": row.take_profit_targets,
        "analysis": row.analysis,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "plan_ids": [target.plan_id for target in row.plan_targets],
    }


def _serialize_publication(row: SubscriberSignalPublication) -> dict:
    return {
        "id": row.id,
        "subscriber_signal_id": row.subscriber_signal_id,
        "signal_plan_target_id": row.signal_plan_target_id,
        "plan_channel_mapping_id": row.plan_channel_mapping_id,
        "subscription_plan_id": row.subscription_plan_id,
        "telegram_channel_id": row.telegram_channel_id,
        "status": row.status.value,
        "attempt_count": row.attempt_count,
        "last_attempt_at": row.last_attempt_at.isoformat() if row.last_attempt_at else None,
        "next_attempt_at": row.next_attempt_at.isoformat() if row.next_attempt_at else None,
        "processing_started_at": row.processing_started_at.isoformat()
        if row.processing_started_at
        else None,
        "provider_message_reference": row.provider_message_reference,
        "telegram_chat_id": row.telegram_chat_id,
        "telegram_message_id": row.telegram_message_id,
        "published_at": row.published_at.isoformat() if row.published_at else None,
        "failed_at": row.failed_at.isoformat() if row.failed_at else None,
        "cancelled_at": row.cancelled_at.isoformat() if row.cancelled_at else None,
        "last_error_code": row.last_error_code,
        "last_error_message": row.last_error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_delivery_attempt(row: SubscriberSignalDeliveryAttempt) -> dict:
    return {
        "id": row.id,
        "signal_publication_id": row.signal_publication_id,
        "attempt_number": row.attempt_number,
        "processing_claim_id": row.processing_claim_id,
        "outcome": row.outcome.value,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "telegram_chat_id": row.telegram_chat_id,
        "telegram_message_id": row.telegram_message_id,
        "provider_message_reference": row.provider_message_reference,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "is_retryable": row.is_retryable,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@signal_router.post("")
def create_signal(
    body: SignalDraftRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    try:
        row = create_signal_draft(
            db,
            admin_user_id=admin.id,
            symbol=body.symbol,
            direction=SubscriberSignalDirection(body.direction),
            entry=body.entry,
            stop_loss=body.stop_loss,
            take_profit_targets=body.take_profit_targets,
            analysis=body.analysis,
            expires_at=body.expires_at,
            plan_ids=body.plan_ids,
            now=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize_signal(row)


@signal_router.get("")
def list_signals(
    status: Literal["draft", "approved", "cancelled"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    after_signal_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    del admin
    query = db.query(SubscriberSignal)
    if status:
        query = query.filter(SubscriberSignal.status == SubscriberSignalStatus(status))
    if after_signal_id:
        query = query.filter(SubscriberSignal.id > after_signal_id)
    rows = query.order_by(SubscriberSignal.id.asc()).limit(limit).all()
    return {"items": [_serialize_signal(row) for row in rows]}


@signal_router.patch("/{signal_id}")
def update_signal(
    signal_id: str,
    body: SignalDraftUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    updates = body.model_dump(exclude_unset=True)
    if "direction" in updates and updates["direction"] is not None:
        updates["direction"] = SubscriberSignalDirection(updates["direction"])
    try:
        row = update_signal_draft(
            db,
            signal_id=signal_id,
            admin_user_id=admin.id,
            updates=updates,
            now=datetime.now(timezone.utc),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Signal not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize_signal(row)


@signal_router.post("/{signal_id}/approve")
def approve_signal_route(
    signal_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    try:
        row = approve_signal(
            db,
            signal_id=signal_id,
            admin_user_id=admin.id,
            now=datetime.now(timezone.utc),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Signal not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize_signal(row)


@signal_router.post("/{signal_id}/cancel")
def cancel_signal_route(
    signal_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    try:
        row = cancel_signal(
            db,
            signal_id=signal_id,
            admin_user_id=admin.id,
            now=datetime.now(timezone.utc),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Signal not found")
    return _serialize_signal(row)


@publication_router.get("")
def list_publications(
    status: Literal[
        "pending",
        "processing",
        "published",
        "retryable_failure",
        "terminal_failure",
        "cancelled",
    ]
    | None = Query(default=None),
    signal_id: str | None = Query(default=None),
    plan_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    del admin
    query = db.query(SubscriberSignalPublication)
    if status:
        query = query.filter(SubscriberSignalPublication.status == SignalPublicationStatus(status))
    if signal_id:
        query = query.filter(SubscriberSignalPublication.subscriber_signal_id == signal_id)
    if plan_id:
        query = query.filter(SubscriberSignalPublication.subscription_plan_id == plan_id)
    rows = (
        query.order_by(
            SubscriberSignalPublication.updated_at.desc(),
            SubscriberSignalPublication.id.desc(),
        )
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    return {
        "items": [_serialize_publication(row) for row in rows[:limit]],
        "has_more": has_more,
    }


@publication_router.get("/{publication_id}")
def get_publication(
    publication_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    del admin
    row = db.get(SubscriberSignalPublication, publication_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    return _serialize_publication(row)


@publication_router.get("/{publication_id}/attempts")
def list_publication_attempts(
    publication_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    before_attempt_number: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    del admin
    if db.get(SubscriberSignalPublication, publication_id) is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    query = db.query(SubscriberSignalDeliveryAttempt).filter(
        SubscriberSignalDeliveryAttempt.signal_publication_id == publication_id
    )
    if before_attempt_number is not None:
        query = query.filter(
            SubscriberSignalDeliveryAttempt.attempt_number < before_attempt_number
        )
    rows = (
        query.order_by(SubscriberSignalDeliveryAttempt.attempt_number.desc())
        .limit(limit + 1)
        .all()
    )
    page = rows[:limit]
    has_more = len(rows) > limit
    return {
        "items": [_serialize_delivery_attempt(row) for row in page],
        "has_more": has_more,
        "next_before_attempt_number": page[-1].attempt_number if has_more and page else None,
    }


@publication_router.post("/process-due")
async def process_due_publications(
    body: ProcessDueRequest | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    request_body = body or ProcessDueRequest()
    now = datetime.now(timezone.utc)
    record_manual_signal_processing_requested(
        db,
        admin_user_id=admin.id,
        limit=request_body.limit,
        now=now,
    )
    result = await process_due_signal_publications(limit=request_body.limit, now=now)
    return {
        "processed": result.processed,
        "published": result.published,
        "retryable_failures": result.retryable_failures,
        "terminal_failures": result.terminal_failures,
        "cancelled": result.cancelled,
    }


@publication_router.post("/backfill")
def backfill_publications(
    body: SignalBackfillRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    try:
        return backfill_missing_signal_publications(
            db,
            now=datetime.now(timezone.utc),
            admin_user_id=admin.id,
            signal_id=body.signal_id,
            dry_run=body.dry_run,
            limit=body.limit,
            after_signal_id=body.after_signal_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@publication_router.post("/{publication_id}/retry")
def retry_publication(
    publication_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    try:
        row = retry_signal_publication(
            db,
            publication_id=publication_id,
            admin_user_id=admin.id,
            now=datetime.now(timezone.utc),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Publication not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _serialize_publication(row)
