import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


BACKEND_DIR = Path(__file__).resolve().parents[1]
PHASE_8_REVISION = "b8e2f4a6c901"
PHASE_9_REVISION = "c3d9e1f7a204"


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _publication_columns(connection: sqlite3.Connection) -> set[str]:
    return {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info('subscriber_signal_publications')"
        )
    }


def test_phase9_delivery_attempt_migration_round_trip(tmp_path, monkeypatch):
    database_path = tmp_path / "phase9-migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _config(database_url)

    command.upgrade(config, PHASE_8_REVISION)
    command.upgrade(config, PHASE_9_REVISION)

    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        columns = _publication_columns(connection)
        attempt_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='subscriber_signal_delivery_attempts'"
        ).fetchone()[0]
    finally:
        connection.close()

    assert "subscriber_signal_delivery_attempts" in tables
    assert {
        "last_attempt_at",
        "telegram_chat_id",
        "telegram_message_id",
        "cancelled_at",
        "last_error_message",
    }.issubset(columns)
    assert "signal_delivery_attempt_outcome" in attempt_sql
    assert "uq_signal_delivery_attempt_number" in attempt_sql
    assert "uq_signal_delivery_attempt_claim" in attempt_sql

    command.downgrade(config, PHASE_8_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        columns = _publication_columns(connection)
    finally:
        connection.close()

    assert "subscriber_signal_delivery_attempts" not in tables
    assert "last_attempt_at" not in columns
    assert "telegram_message_id" not in columns

    command.upgrade(config, "head")
    command.check(config)


def test_phase9_attempt_constraints(tmp_path, monkeypatch):
    database_path = tmp_path / "phase9-constraints.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _config(database_url)
    command.upgrade(config, "head")

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_signal_delivery_attempts (
                    id, signal_publication_id, attempt_number,
                    processing_claim_id, outcome, started_at, created_at
                ) VALUES (
                    'attempt-bad', 'missing-publication', 0,
                    'claim-1', 'processing',
                    '2026-07-28 12:00:00+00:00',
                    '2026-07-28 12:00:00+00:00'
                )
                """
            )
    finally:
        connection.close()
