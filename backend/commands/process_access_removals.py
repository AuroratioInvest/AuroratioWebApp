"""Run one bounded pass of expired Telegram membership removals.

Usage from the repository root:

    python -m backend.commands.process_access_removals --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.telegram_membership_service import (  # noqa: E402
    MEMBERSHIP_PROCESS_MAX_LIMIT,
    process_due_membership_removals,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process due Telegram membership removals."
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--now",
        type=str,
        default=None,
        help="Override current UTC time for controlled testing (ISO 8601).",
    )
    args = parser.parse_args(argv)

    if args.limit < 1 or args.limit > MEMBERSHIP_PROCESS_MAX_LIMIT:
        print(
            f"error: --limit must be between 1 and {MEMBERSHIP_PROCESS_MAX_LIMIT}",
            file=sys.stderr,
        )
        return 2
    
    effective_now = datetime.now(timezone.utc)

    if args.now:
        try:
            effective_now = datetime.fromisoformat(
                args.now.replace("Z", "+00:00")
            )
            if effective_now.tzinfo is None:
                raise ValueError
            effective_now = effective_now.astimezone(timezone.utc)
        except ValueError:
            print(
                "error: --now must be a timezone-aware ISO 8601 datetime",
                file=sys.stderr,
            )
            return 2
        
    result = asyncio.run(
        process_due_membership_removals(
            limit=args.limit,
            now=effective_now,
        )
    )
    print(
        json.dumps(
            {
                "processed": result.processed,
                "removed": result.removed,
                "retryable_failures": result.retryable_failures,
                "terminal_failures": result.terminal_failures,
                "retained": result.retained,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
