from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from database import get_db
from dependencies import require_active_admin
from models import User
from services.subscriber_fulfillment_service import (
    FULFILLMENT_BACKFILL_DEFAULT_LIMIT,
    FULFILLMENT_BACKFILL_MAX_LIMIT,
    FULFILLMENT_PROCESS_DEFAULT_LIMIT,
    FULFILLMENT_PROCESS_MAX_LIMIT,
    enqueue_missing_fulfillments_for_active_entitlements,
    process_due_fulfillments,
    record_manual_due_processing_requested,
    request_manual_fulfillment_retry,
)
from subscriber_models import (
    AccessFulfillmentStatus,
    SubscriberAccessFulfillment,
)

router = APIRouter(
    prefix="/admin/fulfillment",
    tags=["Admin Fulfillment"],
)


class BackfillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entitlement_id: str | None = None
    dry_run: bool = True
    limit: int = Field(
        default=FULFILLMENT_BACKFILL_DEFAULT_LIMIT,
        ge=1,
        le=FULFILLMENT_BACKFILL_MAX_LIMIT,
    )
    after_entitlement_id: str | None = None


class ProcessDueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(
        default=FULFILLMENT_PROCESS_DEFAULT_LIMIT,
        ge=1,
        le=FULFILLMENT_PROCESS_MAX_LIMIT,
    )


def _serialize(row: SubscriberAccessFulfillment) -> dict:
    return {
        "id": row.id,
        "subscriber_id": row.subscriber_id,
        "subscriber_subscription_id": row.subscriber_subscription_id,
        "access_entitlement_id": row.access_entitlement_id,
        "subscription_plan_id": row.subscription_plan_id,
        "telegram_channel_id": row.telegram_channel_id,
        "plan_channel_mapping_id": row.plan_channel_mapping_id,
        "status": row.status.value,
        "attempt_count": row.attempt_count,
        "next_attempt_at": row.next_attempt_at.isoformat()
        if row.next_attempt_at
        else None,
        "last_attempt_at": row.last_attempt_at.isoformat()
        if row.last_attempt_at
        else None,
        "invite_expires_at": row.invite_expires_at.isoformat()
        if row.invite_expires_at
        else None,
        "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
        "failed_at": row.failed_at.isoformat() if row.failed_at else None,
        "last_error_code": row.last_error_code,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("")
def list_fulfillments(
    status: Literal[
        "pending",
        "processing",
        "delivered",
        "retryable_failure",
        "terminal_failure",
        "cancelled",
    ]
    | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    del admin
    query = db.query(SubscriberAccessFulfillment)
    if status:
        query = query.filter(SubscriberAccessFulfillment.status == AccessFulfillmentStatus(status))
    rows = (
        query.order_by(SubscriberAccessFulfillment.updated_at.desc())
        .limit(limit)
        .all()
    )
    return {"items": [_serialize(row) for row in rows]}


@router.post("/process-due")
async def process_due_fulfillment_records(
    body: ProcessDueRequest | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    request_body = body or ProcessDueRequest()
    now = datetime.now(timezone.utc)
    record_manual_due_processing_requested(
        db,
        admin_user_id=admin.id,
        limit=request_body.limit,
        now=now,
    )
    result = await process_due_fulfillments(limit=request_body.limit, now=now)
    return {
        "processed": result.processed,
        "delivered": result.delivered,
        "retryable_failures": result.retryable_failures,
        "terminal_failures": result.terminal_failures,
        "cancelled": result.cancelled,
    }


@router.post("/{fulfillment_id}/retry")
def retry_fulfillment(
    fulfillment_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    try:
        row = request_manual_fulfillment_retry(
            db,
            fulfillment_id=fulfillment_id,
            admin_user_id=admin.id,
            now=datetime.now(timezone.utc),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="Fulfillment not found")
    return _serialize(row)


@router.post("/backfill")
def backfill_fulfillments(
    body: BackfillRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_active_admin),
):
    del admin
    return enqueue_missing_fulfillments_for_active_entitlements(
        db,
        now=datetime.now(timezone.utc),
        entitlement_id=body.entitlement_id,
        dry_run=body.dry_run,
        limit=body.limit,
        after_entitlement_id=body.after_entitlement_id,
    )
