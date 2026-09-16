from __future__ import annotations

import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from models import DailyBotReport


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_summary_text(summary: dict) -> str:
    lines = [
        "AURORATIO DAILY BOT REPORT",
        "=" * 42,
        f"Mode: {summary.get('mode')}",
        f"Started: {summary.get('started_at')}",
        f"Finished: {summary.get('finished_at')}",
        "",
        "Execution Summary",
        "-" * 42,
        f"Users checked: {summary.get('users_checked', 0)}",
        f"Users skipped: {summary.get('users_skipped', summary.get('skipped', 0))}",
        f"Signals detected: {summary.get('signals', 0)}",
        f"Executed: {summary.get('executed', 0)}",
        f"Failed: {summary.get('failed', 0)}",
        f"Skipped: {summary.get('skipped', 0)}",
    ]

    if summary.get("error"):
        lines.extend(["", "Error", "-" * 42, str(summary["error"])])

    return "\n".join(lines)


def create_daily_bot_report(
    db: Session,
    *,
    summary: dict,
    triggered_by: str = "scheduler",
    error_message: str | None = None,
) -> DailyBotReport:
    report = DailyBotReport(
        run_date=utc_now(),
        started_at=_parse_dt(summary.get("started_at")),
        finished_at=_parse_dt(summary.get("finished_at")),
        mode=summary.get("mode"),
        triggered_by=triggered_by,
        users_checked=int(summary.get("users_checked", 0)),
        users_skipped=int(summary.get("users_skipped", summary.get("skipped", 0))),
        signals_detected=int(summary.get("signals", 0)),
        executed=int(summary.get("executed", 0)),
        failed=int(summary.get("failed", 0)),
        skipped=int(summary.get("skipped", 0)),
        summary_text=build_summary_text(summary),
        raw_summary=json.dumps(summary, default=str),
        error_message=error_message,
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    return report


def get_latest_daily_bot_report(db: Session) -> DailyBotReport | None:
    return (
        db.query(DailyBotReport)
        .order_by(DailyBotReport.created_at.desc())
        .first()
    )


def get_daily_bot_reports(db: Session, limit: int = 20) -> list[DailyBotReport]:
    return (
        db.query(DailyBotReport)
        .order_by(DailyBotReport.created_at.desc())
        .limit(limit)
        .all()
    )


def serialize_daily_bot_report(report: DailyBotReport) -> dict:
    return {
        "id": report.id,
        "run_date": report.run_date.isoformat() if report.run_date else None,
        "started_at": report.started_at.isoformat() if report.started_at else None,
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
        "mode": report.mode,
        "triggered_by": report.triggered_by,
        "users_checked": report.users_checked,
        "users_skipped": report.users_skipped,
        "signals_detected": report.signals_detected,
        "executed": report.executed,
        "failed": report.failed,
        "skipped": report.skipped,
        "summary_text": report.summary_text,
        "raw_summary": report.raw_summary,
        "error_message": report.error_message,
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


def _parse_dt(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None