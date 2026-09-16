"""Run one bounded pass of durable private-channel access fulfillment work.

Usage from the repository root:

    python -m backend.commands.process_access_fulfillments --limit 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

RESULT_FIELDS = (
    "processed",
    "delivered",
    "retryable_failures",
    "terminal_failures",
    "cancelled",
)


def _load_fulfillment_service() -> Any:
    import models  # noqa: F401
    from services import subscriber_fulfillment_service

    return subscriber_fulfillment_service


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process one bounded pass of due private-channel access fulfillments."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum due fulfillment records to process in this invocation.",
    )
    return parser


def _safe_result_payload(result: Any) -> dict[str, int]:
    return {field: int(getattr(result, field, 0) or 0) for field in RESULT_FIELDS}


async def _run_once(*, service: Any, limit: int) -> dict[str, int]:
    result = await service.process_due_fulfillments(
        limit=limit,
        now=datetime.now(timezone.utc),
    )
    return _safe_result_payload(result)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        service = _load_fulfillment_service()
    except Exception:
        logger.error("Failed to initialize access fulfillment worker")
        print("fatal: access fulfillment worker initialization failed", file=sys.stderr)
        return 1

    max_limit = int(service.FULFILLMENT_PROCESS_MAX_LIMIT)
    if args.limit < 1 or args.limit > max_limit:
        print(f"error: --limit must be between 1 and {max_limit}", file=sys.stderr)
        return 2

    try:
        payload = asyncio.run(_run_once(service=service, limit=args.limit))
    except Exception:
        logger.error("Access fulfillment worker failed")
        print("fatal: access fulfillment worker execution failed", file=sys.stderr)
        return 1

    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
