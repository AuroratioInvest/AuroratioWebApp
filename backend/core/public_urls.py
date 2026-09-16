"""Trusted public application URL configuration."""

import os
from urllib.parse import urlsplit, urlunsplit


class PublicAppUrlConfigurationError(ValueError):
    pass


def public_app_origin(*, required: bool = True) -> str | None:
    raw_value = os.getenv("PUBLIC_APP_URL")
    if not raw_value or not raw_value.strip():
        if required:
            raise PublicAppUrlConfigurationError("PUBLIC_APP_URL is not configured")
        return None

    parsed = urlsplit(raw_value.strip())
    is_local_http = (
        parsed.scheme == "http"
        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    )
    if parsed.scheme != "https" and not is_local_http:
        raise PublicAppUrlConfigurationError(
            "PUBLIC_APP_URL must use HTTPS outside local development"
        )
    if (
        not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise PublicAppUrlConfigurationError(
            "PUBLIC_APP_URL must be a trusted origin without a path or credentials"
        )

    return urlunsplit((parsed.scheme, parsed.netloc, "", "", "")).rstrip("/")
