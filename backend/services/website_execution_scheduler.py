from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from apscheduler.events import (
    EVENT_JOB_ERROR,
    EVENT_JOB_EXECUTED,
    JobExecutionEvent,
)
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import SessionLocal
from core.features import legacy_customer_app_enabled
from services.website_execution_service import (
    execution_mode,
    run_website_execution,
)

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_create_daily_report(
    *,
    db,
    summary: dict,
    triggered_by: str,
    error_message: str | None = None,
) -> None:
    try:
        from services.daily_report_service import create_daily_bot_report

        create_daily_bot_report(
            db,
            summary=summary,
            triggered_by=triggered_by,
            error_message=error_message,
        )

    except Exception:
        logger.exception("Could not save daily bot report")


def _run_job() -> None:
    """
    Main scheduled execution entrypoint.

    Safety guarantees:
    - one scheduler instance
    - one job instance at a time
    - dry-run by default
    - FA eligibility checked before execution
    - per-user failure isolation
    - summary always persisted
    """

    if not legacy_customer_app_enabled():
        logger.info("Legacy customer execution job skipped: feature disabled")
        return

    logger.info(
        "Starting scheduled AuroRatio execution job. mode=%s",
        execution_mode(),
    )

    db = SessionLocal()

    try:
        summary = run_website_execution(db)

        _safe_create_daily_report(
            db=db,
            summary=summary,
            triggered_by="scheduler",
        )

        logger.info("AuroRatio scheduled execution completed: %s", summary)

    except Exception as exc:
        logger.exception("AuroRatio scheduled execution failed")

        summary = {
            "mode": execution_mode(),
            "provider": "ibkr_fa",
            "started_at": utc_now().isoformat(),
            "finished_at": utc_now().isoformat(),
            "users_checked": 0,
            "signals": 0,
            "executed": 0,
            "failed": 1,
            "skipped": 0,
            "error": str(exc),
        }

        _safe_create_daily_report(
            db=db,
            summary=summary,
            triggered_by="scheduler",
            error_message=str(exc),
        )

    finally:
        db.close()


def _job_listener(event: JobExecutionEvent) -> None:
    if event.exception:
        logger.error(
            "Scheduler job crashed: job_id=%s exception=%s",
            event.job_id,
            event.exception,
        )
    else:
        logger.info(
            "Scheduler job completed successfully: job_id=%s",
            event.job_id,
        )


def start_execution_scheduler() -> None:
    """
    Starts APScheduler background execution.

    Environment variables:
    - AURORATIO_ENABLE_WEBSITE_SCHEDULER=true
    - AURORATIO_EXECUTION_HOUR=17
    - AURORATIO_EXECUTION_MINUTE=5
    - AURORATIO_EXECUTION_TIMEZONE=Europe/Paris

    Execution modes:
    - disabled
    - dry_run
    - live
    """

    global _scheduler

    if not legacy_customer_app_enabled():
        logger.info("AuroRatio scheduler disabled with legacy customer application")
        return

    enabled = (
        os.getenv("AURORATIO_ENABLE_WEBSITE_SCHEDULER", "false")
        .strip()
        .lower()
    )

    if enabled != "true":
        logger.info("AuroRatio scheduler disabled by environment")
        return

    if _scheduler and _scheduler.running:
        logger.info("AuroRatio scheduler already running")
        return

    hour = int(os.getenv("AURORATIO_EXECUTION_HOUR", "17"))
    minute = int(os.getenv("AURORATIO_EXECUTION_MINUTE", "5"))
    timezone_name = os.getenv(
        "AURORATIO_EXECUTION_TIMEZONE",
        "Europe/Paris",
    )

    _scheduler = BackgroundScheduler(
        timezone=timezone_name,
        job_defaults={
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 3600,
        },
    )

    _scheduler.add_listener(
        _job_listener,
        EVENT_JOB_EXECUTED | EVENT_JOB_ERROR,
    )

    _scheduler.add_job(
        _run_job,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=hour,
            minute=minute,
            timezone=timezone_name,
        ),
        id="auroratio_website_execution",
        name="AuroRatio Website Execution",
        replace_existing=True,
    )

    _scheduler.start()

    logger.info(
        (
            "AuroRatio execution scheduler started | "
            "schedule=mon-fri %02d:%02d %s | "
            "mode=%s"
        ),
        hour,
        minute,
        timezone_name,
        execution_mode(),
    )


def stop_execution_scheduler() -> None:
    global _scheduler

    if not _scheduler:
        return

    if _scheduler.running:
        logger.info("Stopping AuroRatio execution scheduler")
        _scheduler.shutdown(wait=False)

    _scheduler = None
