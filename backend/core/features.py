import os

from fastapi import HTTPException


TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def parse_boolean_flag(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in TRUE_VALUES


def legacy_customer_app_enabled() -> bool:
    return parse_boolean_flag(os.getenv("LEGACY_CUSTOMER_APP_ENABLED"))


def require_legacy_customer_app() -> None:
    if not legacy_customer_app_enabled():
        raise HTTPException(status_code=404, detail="Not found")
