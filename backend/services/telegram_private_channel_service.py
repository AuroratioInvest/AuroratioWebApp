"""Internal Telegram private-channel invite provider.

This module is intentionally backend-only. Public frontend copy and public API
responses must continue to use provider-neutral private-channel wording.
"""

from __future__ import annotations

import logging
import os
import re
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

TOKEN_PATTERN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
INVITE_PATTERN = re.compile(r"https://(?:t\.me|telegram\.me)/[^\s]+")
INVITE_PATH_PATTERN = re.compile(r"^/(?:\+[A-Za-z0-9_-]+|joinchat/[A-Za-z0-9_-]+)$")
INVALID_PERCENT_ENCODING_PATTERN = re.compile(r"%(?![0-9A-Fa-f]{2})")


class TelegramProviderError(Exception):
    error_code = "telegram_provider_error"
    retryable = True


class TelegramConfigurationError(TelegramProviderError):
    error_code = "telegram_configuration_error"
    retryable = False


class TelegramPermanentError(TelegramProviderError):
    error_code = "telegram_permanent_error"
    retryable = False


class TelegramRateLimitError(TelegramProviderError):
    error_code = "telegram_rate_limited"
    retryable = True

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class TelegramInvite:
    invite_url: str
    provider_reference: str
    expires_at: datetime


@dataclass(frozen=True)
class TelegramPublishedMessage:
    provider_reference: str
    message_id: int


def sanitize_telegram_error(exc: Exception) -> str:
    text = TOKEN_PATTERN.sub("[redacted-token]", str(exc))
    text = INVITE_PATTERN.sub("[redacted-invite]", text)
    return " ".join(text.split())[:500]


def telegram_bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise TelegramConfigurationError("TELEGRAM_BOT_TOKEN is not configured")
    return token


def telegram_api_base_url() -> str:
    value = os.getenv("TELEGRAM_API_BASE_URL", "https://api.telegram.org").strip()
    if not value:
        raise TelegramConfigurationError("TELEGRAM_API_BASE_URL is invalid")
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise TelegramConfigurationError("TELEGRAM_API_BASE_URL must be an HTTPS origin")
    return value.rstrip("/")


def telegram_invite_ttl_hours() -> int:
    raw = os.getenv("TELEGRAM_INVITE_TTL_HOURS", "24")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise TelegramConfigurationError("TELEGRAM_INVITE_TTL_HOURS is invalid") from exc
    if value <= 0 or value > 168:
        raise TelegramConfigurationError("TELEGRAM_INVITE_TTL_HOURS is invalid")
    return value


def telegram_provider_timeout_seconds() -> float:
    raw = os.getenv("TELEGRAM_PROVIDER_TIMEOUT_SECONDS", "10")
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise TelegramConfigurationError("TELEGRAM_PROVIDER_TIMEOUT_SECONDS is invalid") from exc
    if value <= 0 or value > 60:
        raise TelegramConfigurationError("TELEGRAM_PROVIDER_TIMEOUT_SECONDS is invalid")
    return value


def validate_telegram_invite_url(invite_url: str) -> str:
    if not isinstance(invite_url, str) or not invite_url.strip():
        raise TelegramPermanentError("Telegram invite URL is missing")
    candidate = invite_url.strip()
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise TelegramPermanentError("Telegram invite URL is malformed") from exc
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or hostname not in {"t.me", "telegram.me"}:
        raise TelegramPermanentError("Telegram invite URL is not trusted")
    if port not in {None, 443}:
        raise TelegramPermanentError("Telegram invite URL contains an unexpected port")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise TelegramPermanentError("Telegram invite URL contains unexpected components")
    path = parsed.path or ""
    if INVALID_PERCENT_ENCODING_PATTERN.search(path):
        raise TelegramPermanentError("Telegram invite URL path is malformed")
    if not INVITE_PATH_PATTERN.fullmatch(path):
        raise TelegramPermanentError("Telegram invite URL path is not an invite")
    return candidate


def _provider_reference(invite_url: str) -> str:
    # Telegram's Bot API returns the invite link as the stable revocation handle.
    # The full invite URL is secret, so retain only a short non-reversible
    # operational reference. Revocation receives the in-memory URL before email
    # failure retries; later retry attempts generate a fresh invite.
    return f"tg_invite:{hashlib.sha256(invite_url.encode('utf-8')).hexdigest()[:16]}"


def telegram_invite_provider_reference(invite_url: str) -> str:
    """Return the stable non-secret provider reference for a Telegram invite URL."""
    return _provider_reference(invite_url)


class TelegramPrivateChannelService:
    def __init__(
        self,
        *,
        bot_token: str | None = None,
        api_base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._bot_token = bot_token
        self._api_base_url = api_base_url
        self._timeout_seconds = timeout_seconds

    @property
    def bot_token(self) -> str:
        return self._bot_token or telegram_bot_token()

    @property
    def api_base_url(self) -> str:
        return self._api_base_url or telegram_api_base_url()

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds or telegram_provider_timeout_seconds()

    def _url(self, method: str) -> str:
        return f"{self.api_base_url}/bot{self.bot_token}/{method}"

    async def create_single_use_invite(
        self,
        *,
        chat_id: int,
        name: str,
        expires_at: datetime,
    ) -> TelegramInvite:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise TelegramPermanentError("Telegram invite expiry must be timezone-aware")
        expire_timestamp = int(expires_at.astimezone(timezone.utc).timestamp())
        payload = {
            "chat_id": chat_id,
            "name": name[:32],
            "expire_date": expire_timestamp,
            "member_limit": 1,
            "creates_join_request": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self._url("createChatInviteLink"), json=payload)
        except httpx.TimeoutException as exc:
            raise TelegramProviderError("Telegram invite creation timed out") from exc
        except httpx.HTTPError as exc:
            raise TelegramProviderError("Telegram invite creation failed") from exc

        data = self._parse_response(response, "Telegram invite creation failed")
        result = data.get("result") or {}
        invite_url = validate_telegram_invite_url(result.get("invite_link"))
        return TelegramInvite(
            invite_url=invite_url,
            provider_reference=_provider_reference(invite_url),
            expires_at=expires_at.astimezone(timezone.utc),
        )

    async def revoke_invite(self, *, chat_id: int, invite_url: str) -> bool:
        try:
            invite_url = validate_telegram_invite_url(invite_url)
        except TelegramProviderError:
            return False
        payload = {"chat_id": chat_id, "invite_link": invite_url}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self._url("revokeChatInviteLink"), json=payload)
            self._parse_response(response, "Telegram invite revocation failed")
            return True
        except TelegramProviderError:
            return False
        except httpx.HTTPError:
            return False

    async def remove_member(self, *, chat_id: int, user_id: int) -> None:
        """Remove a member while allowing a future rejoin with a new invite.

        Telegram requires a ban to force removal. The member is immediately
        unbanned with only_if_banned=True so a later paid subscription can join
        again with a fresh invite.
        """
        if not isinstance(chat_id, int):
            raise TelegramPermanentError("Telegram chat id is invalid")
        if not isinstance(user_id, int) or user_id <= 0:
            raise TelegramPermanentError("Telegram user id is invalid")

        ban_payload = {
            "chat_id": chat_id,
            "user_id": user_id,
            "revoke_messages": False,
        }
        unban_payload = {
            "chat_id": chat_id,
            "user_id": user_id,
            "only_if_banned": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                ban_response = await client.post(
                    self._url("banChatMember"),
                    json=ban_payload,
                )
                self._parse_response(
                    ban_response,
                    "Telegram member removal failed",
                )

                unban_response = await client.post(
                    self._url("unbanChatMember"),
                    json=unban_payload,
                )
                self._parse_response(
                    unban_response,
                    "Telegram member unban failed",
                )
        except httpx.TimeoutException as exc:
            raise TelegramProviderError(
                "Telegram member removal timed out"
            ) from exc
        except httpx.HTTPError as exc:
            raise TelegramProviderError(
                "Telegram member removal failed"
            ) from exc

    async def publish_text_message(
        self,
        *,
        chat_id: int,
        text: str,
    ) -> TelegramPublishedMessage:
        if not isinstance(text, str) or not text.strip():
            raise TelegramPermanentError("Telegram message text is missing")
        if len(text) > 4096:
            raise TelegramPermanentError("Telegram message text is too long")
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self._url("sendMessage"), json=payload)
        except httpx.TimeoutException as exc:
            raise TelegramProviderError("Telegram message publication timed out") from exc
        except httpx.HTTPError as exc:
            raise TelegramProviderError("Telegram message publication failed") from exc

        data = self._parse_response(response, "Telegram message publication failed")
        result = data.get("result") or {}
        message_id = result.get("message_id")
        if not isinstance(message_id, int):
            raise TelegramProviderError("Telegram message response missing message id")
        return TelegramPublishedMessage(
            provider_reference=f"tg_message:{message_id}",
            message_id=message_id,
        )

    @staticmethod
    def _parse_response(response: httpx.Response, message: str) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramProviderError(message) from exc
        if response.status_code >= 400 or not data.get("ok"):
            description = str(data.get("description") or message)
            lowered = description.lower()
            parameters = data.get("parameters") or {}
            retry_after = None
            if isinstance(parameters, dict):
                raw_retry_after = parameters.get("retry_after")
                if isinstance(raw_retry_after, int) and raw_retry_after > 0:
                    retry_after = raw_retry_after
            if response.status_code == 429:
                raise TelegramRateLimitError(
                    description,
                    retry_after_seconds=retry_after,
                )
            if response.status_code in {400, 401, 403}:
                raise TelegramPermanentError(description)
            if "not enough rights" in lowered or "administrator" in lowered:
                raise TelegramPermanentError(description)
            raise TelegramProviderError(description)
        return data
