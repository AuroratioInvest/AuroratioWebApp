"""Read-only private-channel operations summaries for authenticated admins."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from subscriber_models import (
    AccessFulfillmentStatus,
    PlanChannelMapping,
    SignalPublicationStatus,
    SubscriberAccessFulfillment,
    SubscriberSignal,
    SubscriberSignalPublication,
    SubscriberSignalStatus,
    SubscriptionPlan,
    TelegramChannel,
)


CHANNEL_CONFIGURATION_DEFAULT_LIMIT = 50
CHANNEL_CONFIGURATION_MAX_LIMIT = 100
PROVIDER_NAME_PATTERN = re.compile("telegram", re.IGNORECASE)


def provider_credentials_configured() -> bool:
    """Return a safe boolean for server-side private-channel credentials."""

    return bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip())


def _neutral_text(value: str | None) -> str | None:
    if value is None:
        return None
    return PROVIDER_NAME_PATTERN.sub("Private Channel", value)


def _enum_counts(db: Session, model, column, values: Iterable) -> dict[str, int]:
    counts = {value.value: 0 for value in values}
    rows = db.query(column, func.count(model.id)).group_by(column).all()
    for status, count in rows:
        counts[status.value if hasattr(status, "value") else str(status)] = int(count)
    return counts


def _scalar_count(db: Session, model, *criteria) -> int:
    query = db.query(func.count(model.id))
    if criteria:
        query = query.filter(*criteria)
    return int(query.scalar() or 0)


def get_private_channel_operations_overview(db: Session) -> dict:
    total_channels = _scalar_count(db, TelegramChannel)
    active_channels = _scalar_count(
        db,
        TelegramChannel,
        TelegramChannel.is_active.is_(True),
        TelegramChannel.archived_at.is_(None),
    )
    configured_channels = _scalar_count(
        db,
        TelegramChannel,
        TelegramChannel.is_configured.is_(True),
        TelegramChannel.archived_at.is_(None),
    )
    ready_channels = _scalar_count(
        db,
        TelegramChannel,
        TelegramChannel.is_active.is_(True),
        TelegramChannel.is_configured.is_(True),
        TelegramChannel.archived_at.is_(None),
        TelegramChannel.telegram_chat_id.isnot(None),
    )
    active_mapping_count = _scalar_count(
        db,
        PlanChannelMapping,
        PlanChannelMapping.is_active.is_(True),
    )
    return {
        "provider_credentials_configured": provider_credentials_configured(),
        "private_channel_counts": {
            "total": total_channels,
            "active": active_channels,
            "configured": configured_channels,
            "ready": ready_channels,
        },
        "active_plan_channel_mapping_count": active_mapping_count,
        "access_fulfillment_counts": _enum_counts(
            db,
            SubscriberAccessFulfillment,
            SubscriberAccessFulfillment.status,
            AccessFulfillmentStatus,
        ),
        "signal_publication_counts": _enum_counts(
            db,
            SubscriberSignalPublication,
            SubscriberSignalPublication.status,
            SignalPublicationStatus,
        ),
        "approved_signal_count": _scalar_count(
            db,
            SubscriberSignal,
            SubscriberSignal.status == SubscriberSignalStatus.approved,
        ),
        "draft_signal_count": _scalar_count(
            db,
            SubscriberSignal,
            SubscriberSignal.status == SubscriberSignalStatus.draft,
        ),
    }


def list_private_channel_configuration(
    db: Session,
    *,
    limit: int = CHANNEL_CONFIGURATION_DEFAULT_LIMIT,
    after_channel_id: str | None = None,
) -> dict:
    if limit <= 0 or limit > CHANNEL_CONFIGURATION_MAX_LIMIT:
        raise ValueError("Channel configuration limit is outside the allowed range")

    query = db.query(TelegramChannel)
    if after_channel_id:
        query = query.filter(TelegramChannel.id > after_channel_id)
    rows = (
        query.order_by(TelegramChannel.id.asc())
        .limit(limit + 1)
        .all()
    )
    page = rows[:limit]
    has_more = len(rows) > limit
    channel_ids = [row.id for row in page]
    mappings_by_channel: dict[str, list[tuple[PlanChannelMapping, SubscriptionPlan]]] = {
        channel_id: [] for channel_id in channel_ids
    }
    if channel_ids:
        mapping_rows = (
            db.query(PlanChannelMapping, SubscriptionPlan)
            .join(SubscriptionPlan, SubscriptionPlan.id == PlanChannelMapping.plan_id)
            .filter(PlanChannelMapping.channel_id.in_(channel_ids))
            .order_by(
                PlanChannelMapping.channel_id.asc(),
                SubscriptionPlan.code.asc(),
                PlanChannelMapping.id.asc(),
            )
            .all()
        )
        for mapping, plan in mapping_rows:
            mappings_by_channel.setdefault(mapping.channel_id, []).append((mapping, plan))

    items = []
    for channel in page:
        archived = channel.archived_at is not None
        items.append(
            {
                "private_channel_id": channel.id,
                "channel_code": _neutral_text(channel.code),
                "display_name_en": _neutral_text(channel.display_name_en),
                "display_name_fr": _neutral_text(channel.display_name_fr),
                "is_active": bool(channel.is_active),
                "is_configured": bool(channel.is_configured),
                "is_archived": archived,
                "has_provider_target": channel.telegram_chat_id is not None,
                "is_ready": bool(
                    channel.is_active
                    and channel.is_configured
                    and not archived
                    and channel.telegram_chat_id is not None
                ),
                "mappings": [
                    {
                        "mapping_id": mapping.id,
                        "plan_id": plan.id,
                        "plan_code": _neutral_text(plan.code),
                        "plan_display_name_en": _neutral_text(plan.display_name_en),
                        "plan_display_name_fr": _neutral_text(plan.display_name_fr),
                        "is_active": bool(mapping.is_active),
                    }
                    for mapping, plan in mappings_by_channel.get(channel.id, [])
                ],
            }
        )

    return {
        "items": items,
        "limit": limit,
        "has_more": has_more,
        "next_cursor": page[-1].id if has_more and page else None,
    }
