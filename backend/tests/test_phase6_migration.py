import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


BACKEND_DIR = Path(__file__).resolve().parents[1]
PREVIOUS_REVISION = "8c4f2a1d9b73"
PHASE_6_REVISION = "d2a7f6c9b104"


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_phase6_portal_token_migration_upgrade_downgrade_and_reupgrade(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "phase6-migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _config(database_url)

    command.upgrade(config, PREVIOUS_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            INSERT INTO subscribers (
                id, stripe_customer_id, stripe_email, normalized_email,
                preferred_language, billing_country, created_at, updated_at,
                archived_at
            ) VALUES (
                'subscriber-phase6', 'cus_phase6', 'billing@example.com',
                'billing@example.com', 'en', NULL,
                '2026-07-27 12:00:00+00:00',
                '2026-07-27 12:00:00+00:00', NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(config, PHASE_6_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        constraints_sql = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'portal_access_tokens'
            """
        ).fetchone()[0]
        issuance_constraints_sql = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'portal_link_issuances'
            """
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO portal_access_tokens (
                id, token_hash, subscriber_id, stripe_customer_id, purpose, expires_at,
                consumed_at, invalidated_at, correlation_id, created_at,
                updated_at
            ) VALUES (
                'token-phase6',
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                'subscriber-phase6', 'cus_phase6', 'customer_portal',
                '2026-07-27 12:15:00+00:00', NULL, NULL,
                'correlation-phase6',
                '2026-07-27 12:00:00+00:00',
                '2026-07-27 12:00:00+00:00'
            )
            """
        )
        connection.commit()
        assert "portal_access_tokens" in tables
        assert "portal_link_issuances" in tables
        assert "portal_access_token_purpose" in constraints_sql
        assert "ck_portal_access_token_hash_length" in constraints_sql
        assert (
            "ck_portal_access_token_stripe_customer_id_nonempty"
            in constraints_sql
        )
        assert (
            "uq_portal_link_issuances_subscriber"
            in issuance_constraints_sql
        )
        assert (
            "ck_portal_link_issuance_cooldown"
            in issuance_constraints_sql
        )
    finally:
        connection.close()

    command.downgrade(config, PREVIOUS_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        retained_subscriber = connection.execute(
            """
            SELECT stripe_customer_id, normalized_email
            FROM subscribers WHERE id = 'subscriber-phase6'
            """
        ).fetchone()
        alembic_revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    finally:
        connection.close()

    assert "portal_access_tokens" not in tables
    assert "portal_link_issuances" not in tables
    assert retained_subscriber == ("cus_phase6", "billing@example.com")
    assert alembic_revision == PREVIOUS_REVISION

    command.upgrade(config, "head")
    command.check(config)


def test_phase6_migration_enforces_independent_token_and_issuance_constraints(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "phase6-constraints.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _config(database_url)
    command.upgrade(config, "head")

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.execute(
            """
            INSERT INTO subscribers (
                id, stripe_customer_id, normalized_email,
                created_at, updated_at
            ) VALUES (
                'subscriber-constraints', 'cus_constraints',
                'constraints@example.com',
                '2026-07-27 12:00:00+00:00',
                '2026-07-27 12:00:00+00:00'
            )
            """
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO portal_access_tokens (
                    id, token_hash, subscriber_id, stripe_customer_id,
                    purpose, expires_at,
                    created_at, updated_at
                ) VALUES (
                    'invalid-token-hash', 'short', 'subscriber-constraints',
                    'cus_constraints', 'customer_portal',
                    '2026-07-27 12:15:00+00:00',
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        connection.execute(
            """
            INSERT INTO subscribers (
                id, stripe_customer_id, normalized_email,
                created_at, updated_at
            ) VALUES (
                'subscriber-invalid-cooldown', 'cus_invalid_cooldown',
                'invalid-cooldown@example.com',
                '2026-07-27 12:00:00+00:00',
                '2026-07-27 12:00:00+00:00'
            )
            """
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO portal_access_tokens (
                    id, token_hash, subscriber_id, stripe_customer_id,
                    purpose, expires_at,
                    created_at, updated_at
                ) VALUES (
                    'invalid-token-subscriber',
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                    'missing-subscriber', 'cus_missing', 'customer_portal',
                    '2026-07-27 12:15:00+00:00',
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
            connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO portal_access_tokens (
                    id, token_hash, subscriber_id, stripe_customer_id,
                    purpose, expires_at, created_at, updated_at
                ) VALUES (
                    'invalid-token-customer',
                    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
                    'subscriber-constraints', '   ', 'customer_portal',
                    '2026-07-27 12:15:00+00:00',
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        connection.execute(
            """
            INSERT INTO portal_link_issuances (
                id, subscriber_id, last_issued_at, next_allowed_at,
                created_at, updated_at
            ) VALUES (
                'issuance-valid', 'subscriber-constraints',
                '2026-07-27 12:00:00+00:00',
                '2026-07-27 12:05:00+00:00',
                '2026-07-27 12:00:00+00:00',
                '2026-07-27 12:00:00+00:00'
            )
            """
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO portal_link_issuances (
                    id, subscriber_id, last_issued_at, next_allowed_at,
                    created_at, updated_at
                ) VALUES (
                    'issuance-duplicate', 'subscriber-constraints',
                    '2026-07-27 12:05:00+00:00',
                    '2026-07-27 12:10:00+00:00',
                    '2026-07-27 12:05:00+00:00',
                    '2026-07-27 12:05:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO portal_link_issuances (
                    id, subscriber_id, last_issued_at, next_allowed_at,
                    created_at, updated_at
                ) VALUES (
                    'issuance-invalid-cooldown',
                    'subscriber-invalid-cooldown',
                    '2026-07-27 12:05:00+00:00',
                    '2026-07-27 12:05:00+00:00',
                    '2026-07-27 12:05:00+00:00',
                    '2026-07-27 12:05:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO portal_link_issuances (
                    id, subscriber_id, last_issued_at, next_allowed_at,
                    created_at, updated_at
                ) VALUES (
                    'issuance-missing-subscriber', 'missing-subscriber',
                    '2026-07-27 12:05:00+00:00',
                    '2026-07-27 12:10:00+00:00',
                    '2026-07-27 12:05:00+00:00',
                    '2026-07-27 12:05:00+00:00'
                )
                """
            )
    finally:
        connection.close()
