"""Run one bounded pass of durable subscriber signal publication work.

Usage from the repository root:

    python -m backend.commands.process_signal_publications --limit 1
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
    "published",
    "retryable_failures",
    "terminal_failures",
    "cancelled",
)


def _load_publication_service() -> Any:
    import models  # noqa: F401
    from services import subscriber_signal_publication_service

    return subscriber_signal_publication_service


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process one bounded pass of due subscriber signal publications."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Maximum due publication records to process in this invocation.",
    )
    return parser


def _safe_result_payload(result: Any) -> dict[str, int]:
    return {field: int(getattr(result, field, 0) or 0) for field in RESULT_FIELDS}


async def _run_once(*, service: Any, limit: int) -> dict[str, int]:
    result = await service.process_due_signal_publications(
        limit=limit,
        now=datetime.now(timezone.utc),
    )
    return _safe_result_payload(result)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        service = _load_publication_service()
    except Exception:
        logger.error("Failed to initialize signal publication worker")
        print("fatal: signal publication worker initialization failed", file=sys.stderr)
        return 1

    max_limit = int(service.SIGNAL_PUBLICATION_MAX_LIMIT)
    if args.limit < 1 or args.limit > max_limit:
        print(f"error: --limit must be between 1 and {max_limit}", file=sys.stderr)
        return 2

    try:
        payload = asyncio.run(_run_once(service=service, limit=args.limit))
    except Exception:
        logger.error("Signal publication worker failed")
        print("fatal: signal publication worker execution failed", file=sys.stderr)
        return 1

    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
