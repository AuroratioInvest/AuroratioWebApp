import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


BACKEND_DIR = Path(__file__).resolve().parents[1]
PHASE_7_REVISION = "f4a7b8c9d012"
PHASE_8_REVISION = "b8e2f4a6c901"


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _seed_graph(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        INSERT INTO subscription_plans (
            id, code, display_name_en, display_name_fr, stripe_price_id,
            billing_interval, is_active, is_configured, created_at, updated_at
        ) VALUES
        (
            'plan-phase8', 'monthly-signals', 'Monthly signals',
            'Signaux mensuels', 'price_phase8', 'month', 1, 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        ),
        (
            'plan-phase8-other', 'other-signals', 'Other signals',
            'Autres signaux', 'price_phase8_other', 'month', 1, 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO telegram_channels (
            id, code, telegram_chat_id, display_name_en, display_name_fr,
            is_active, is_configured, created_at, updated_at
        ) VALUES
        (
            'channel-phase8', 'signals', -1001234567890, 'Signals',
            'Signaux', 1, 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        ),
        (
            'channel-phase8-other', 'other-signals', -1009876543210, 'Other Signals',
            'Autres signaux', 1, 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO plan_channel_mappings (
            id, plan_id, channel_id, is_active, created_at, updated_at
        ) VALUES
        (
            'mapping-phase8', 'plan-phase8', 'channel-phase8', 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        ),
        (
            'mapping-phase8-other-plan', 'plan-phase8-other', 'channel-phase8', 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        ),
        (
            'mapping-phase8-other-channel', 'plan-phase8', 'channel-phase8-other', 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO subscriber_signals (
            id, status, symbol, direction, entry, stop_loss, take_profit_targets,
            created_at, updated_at
        ) VALUES (
            'signal-phase8', 'approved', 'XAUUSD', 'buy', '2410',
            '2390', '["2430"]',
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO subscriber_signal_plan_targets (
            id, signal_id, plan_id, created_at
        ) VALUES (
            'target-phase8', 'signal-phase8', 'plan-phase8',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO subscriber_signal_plan_targets (
            id, signal_id, plan_id, created_at
        ) VALUES (
            'target-phase8-other', 'signal-phase8', 'plan-phase8-other',
            '2026-07-27 12:00:00+00:00'
        );
        """
    )
    connection.commit()


def test_phase8_signal_publication_migration_upgrade_downgrade_and_reupgrade(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "phase8-migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _config(database_url)

    command.upgrade(config, PHASE_7_REVISION)
    command.upgrade(config, PHASE_8_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        _seed_graph(connection)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        table_sql = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'subscriber_signal_publications'
            """
        ).fetchone()[0]
        assert "subscriber_signals" in tables
        assert "subscriber_signal_publications" in tables
        assert "signal_publication_status" in table_sql
        assert "fk_signal_publication_target_identity" in table_sql
        assert "fk_signal_publication_mapping_identity" in table_sql
        assert "uq_signal_publication_signal_mapping" in table_sql

        connection.execute(
            """
            INSERT INTO subscriber_signal_publications (
                id, subscriber_signal_id, signal_plan_target_id,
                plan_channel_mapping_id, subscription_plan_id,
                telegram_channel_id, status, attempt_count,
                next_attempt_at, created_at, updated_at
            ) VALUES (
                'publication-phase8', 'signal-phase8', 'target-phase8',
                'mapping-phase8', 'plan-phase8', 'channel-phase8',
                'pending', 0,
                '2026-07-27 12:00:00+00:00',
                '2026-07-27 12:00:00+00:00',
                '2026-07-27 12:00:00+00:00'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    command.downgrade(config, PHASE_7_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        alembic_revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    finally:
        connection.close()
    assert "subscriber_signal_publications" not in tables
    assert alembic_revision == PHASE_7_REVISION

    command.upgrade(config, "head")
    command.check(config)


def test_phase8_migration_enforces_publication_constraints(tmp_path, monkeypatch):
    database_path = tmp_path / "phase8-constraints.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _config(database_url)
    command.upgrade(config, "head")

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        _seed_graph(connection)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_signal_publications (
                    id, subscriber_signal_id, signal_plan_target_id,
                    plan_channel_mapping_id, subscription_plan_id,
                    telegram_channel_id, status, attempt_count,
                    created_at, updated_at
                ) VALUES (
                    'bad-status', 'signal-phase8', 'target-phase8',
                    'mapping-phase8', 'plan-phase8', 'channel-phase8',
                    'not_a_status', 0,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_signal_publications (
                    id, subscriber_signal_id, signal_plan_target_id,
                    plan_channel_mapping_id, subscription_plan_id,
                    telegram_channel_id, status, attempt_count,
                    created_at, updated_at
                ) VALUES (
                    'bad-target-plan', 'signal-phase8', 'target-phase8-other',
                    'mapping-phase8', 'plan-phase8', 'channel-phase8',
                    'pending', 0,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_signal_publications (
                    id, subscriber_signal_id, signal_plan_target_id,
                    plan_channel_mapping_id, subscription_plan_id,
                    telegram_channel_id, status, attempt_count,
                    created_at, updated_at
                ) VALUES (
                    'bad-mapping-plan', 'signal-phase8', 'target-phase8',
                    'mapping-phase8-other-plan', 'plan-phase8',
                    'channel-phase8', 'pending', 0,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_signal_publications (
                    id, subscriber_signal_id, signal_plan_target_id,
                    plan_channel_mapping_id, subscription_plan_id,
                    telegram_channel_id, status, attempt_count,
                    created_at, updated_at
                ) VALUES (
                    'bad-mapping-channel', 'signal-phase8', 'target-phase8',
                    'mapping-phase8-other-channel', 'plan-phase8',
                    'channel-phase8', 'pending', 0,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_signal_publications (
                    id, subscriber_signal_id, signal_plan_target_id,
                    plan_channel_mapping_id, subscription_plan_id,
                    telegram_channel_id, status, attempt_count,
                    created_at, updated_at
                ) VALUES (
                    'bad-attempts', 'signal-phase8', 'target-phase8',
                    'mapping-phase8', 'plan-phase8', 'channel-phase8',
                    'pending', -1,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()
    finally:
        connection.close()

