"""Idempotent bootstrap for the single private subscriber channel.

This module mirrors trusted server configuration into the local database. It
never creates Telegram resources and never repairs conflicting/inactive rows.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from subscriber_models import PlanChannelMapping, SubscriptionPlan, TelegramChannel


DEFAULT_CHANNEL_CODE = "private-signals"
DEFAULT_CHANNEL_DISPLAY_NAME_EN = "AuroRatio Private Signals"
DEFAULT_CHANNEL_DISPLAY_NAME_FR = "Signaux privés AuroRatio"


class PrivateChannelBootstrapConfigurationError(RuntimeError):
    """Trusted private-channel configuration is missing or conflicts with DB state."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise PrivateChannelBootstrapConfigurationError(f"{name} is not configured")
    return value


def configured_channel_id() -> int:
    raw = _required_env("TELEGRAM_CHANNEL_ID")
    try:
        value = int(raw)
    except ValueError as exc:
        raise PrivateChannelBootstrapConfigurationError(
            "TELEGRAM_CHANNEL_ID must be an integer"
        ) from exc
    if value == 0:
        raise PrivateChannelBootstrapConfigurationError(
            "TELEGRAM_CHANNEL_ID must not be zero"
        )
    return value


def configured_channel_code() -> str:
    value = (os.getenv("TELEGRAM_CHANNEL_CODE") or DEFAULT_CHANNEL_CODE).strip()
    if not value:
        raise PrivateChannelBootstrapConfigurationError(
            "TELEGRAM_CHANNEL_CODE is invalid"
        )
    return value


def _configured_display_name(name: str, default: str) -> str:
    value = (os.getenv(name) or default).strip()
    if not value:
        raise PrivateChannelBootstrapConfigurationError(f"{name} is invalid")
    return value


def _valid_channel(row: TelegramChannel | None, *, code: str, chat_id: int) -> bool:
    return (
        row is not None
        and row.code == code
        and row.telegram_chat_id == chat_id
        and row.is_active is True
        and row.is_configured is True
        and row.archived_at is None
    )


def _valid_mapping(
    row: PlanChannelMapping | None,
    *,
    plan_id: str,
    channel_id: str,
) -> bool:
    return (
        row is not None
        and row.plan_id == plan_id
        and row.channel_id == channel_id
        and row.is_active is True
    )


def ensure_private_channel_configured(
    db: Session,
    *,
    now: datetime,
) -> tuple[TelegramChannel, PlanChannelMapping]:
    """Ensure the configured channel and monthly-plan mapping exist.

    The operation is safe to run on every application startup. Missing rows are
    created from trusted environment configuration. Existing rows are validated
    but never overwritten, re-enabled, unarchived, or silently repaired.
    """

    now = _utc(now)
    plan_code = _required_env("MONTHLY_SIGNAL_PLAN_CODE")
    channel_code = configured_channel_code()
    chat_id = configured_channel_id()

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.code == plan_code).first()
    if (
        plan is None
        or plan.is_active is not True
        or plan.is_configured is not True
        or plan.archived_at is not None
    ):
        raise PrivateChannelBootstrapConfigurationError(
            "Configured monthly subscription plan is not ready"
        )

    channel = (
        db.query(TelegramChannel)
        .filter(TelegramChannel.code == channel_code)
        .first()
    )
    if channel is not None:
        if not _valid_channel(channel, code=channel_code, chat_id=chat_id):
            raise PrivateChannelBootstrapConfigurationError(
                "Existing private channel conflicts with trusted configuration"
            )
    else:
        chat_id_owner = (
            db.query(TelegramChannel)
            .filter(TelegramChannel.telegram_chat_id == chat_id)
            .first()
        )
        if chat_id_owner is not None:
            raise PrivateChannelBootstrapConfigurationError(
                "Configured Telegram channel ID is already assigned to another channel"
            )

        channel = TelegramChannel(
            code=channel_code,
            telegram_chat_id=chat_id,
            display_name_en=_configured_display_name(
                "TELEGRAM_CHANNEL_DISPLAY_NAME_EN",
                DEFAULT_CHANNEL_DISPLAY_NAME_EN,
            ),
            display_name_fr=_configured_display_name(
                "TELEGRAM_CHANNEL_DISPLAY_NAME_FR",
                DEFAULT_CHANNEL_DISPLAY_NAME_FR,
            ),
            is_active=True,
            is_configured=True,
            created_at=now,
            updated_at=now,
        )
        db.add(channel)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            channel = (
                db.query(TelegramChannel)
                .filter(TelegramChannel.code == channel_code)
                .first()
            )
            if not _valid_channel(channel, code=channel_code, chat_id=chat_id):
                raise exc

    mapping = (
        db.query(PlanChannelMapping)
        .filter(
            PlanChannelMapping.plan_id == plan.id,
            PlanChannelMapping.channel_id == channel.id,
        )
        .first()
    )
    if mapping is not None:
        if not _valid_mapping(mapping, plan_id=plan.id, channel_id=channel.id):
            raise PrivateChannelBootstrapConfigurationError(
                "Existing plan-to-channel mapping is inactive or conflicting"
            )
        return channel, mapping

    mapping = PlanChannelMapping(
        plan_id=plan.id,
        channel_id=channel.id,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(mapping)
    try:
        db.commit()
        return channel, mapping
    except IntegrityError as exc:
        db.rollback()
        recovered = (
            db.query(PlanChannelMapping)
            .filter(
                PlanChannelMapping.plan_id == plan.id,
                PlanChannelMapping.channel_id == channel.id,
            )
            .first()
        )
        if _valid_mapping(recovered, plan_id=plan.id, channel_id=channel.id):
            return channel, recovered
        raise exc
