"""Create one controlled operational test signal for publication validation.

Usage from the repository root:

    python -m backend.commands.create_test_signal --plan-code monthly-signals
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

SAFE_RESULT_FIELDS = (
    "signal_id",
    "status",
    "created",
    "dry_run",
    "publications_enqueued",
    "would_enqueue_publications",
)


def _is_production() -> bool:
    values = {
        (os.getenv("ENV") or "").strip().lower(),
        (os.getenv("APP_ENV") or "").strip().lower(),
    }
    return bool(values & {"production", "prod"})


def _load_signal_service() -> Any:
    import models  # noqa: F401
    from services import subscriber_signal_publication_service

    return subscriber_signal_publication_service


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create one internal operational test signal and enqueue publication work."
    )
    parser.add_argument(
        "--plan-code",
        required=True,
        help="Trusted subscription plan code that should receive the test signal.",
    )
    parser.add_argument(
        "--test-id",
        default="default",
        help="Stable idempotency key for the operational test signal.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and report expected enqueue count without writing.",
    )
    return parser


def _safe_payload(result: Any, *, plan_code: str) -> dict[str, Any]:
    payload = {field: getattr(result, field) for field in SAFE_RESULT_FIELDS}
    payload["plan_code"] = plan_code
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if _is_production():
        print("error: test signal command is disabled in production", file=sys.stderr)
        return 2

    try:
        service = _load_signal_service()
    except Exception:
        logger.error("Failed to initialize test signal command")
        print("fatal: test signal command initialization failed", file=sys.stderr)
        return 1

    db = service.SessionLocal()
    try:
        result = service.create_operational_test_signal(
            db,
            plan_code=args.plan_code,
            test_id=args.test_id,
            dry_run=args.dry_run,
            now=datetime.now(timezone.utc),
        )
    except Exception:
        db.rollback()
        logger.error("Test signal command failed")
        print("fatal: test signal creation failed", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(json.dumps(_safe_payload(result, plan_code=args.plan_code), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
