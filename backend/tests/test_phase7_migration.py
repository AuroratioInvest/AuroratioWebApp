import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


BACKEND_DIR = Path(__file__).resolve().parents[1]
PHASE_6_REVISION = "d2a7f6c9b104"
PHASE_7_REVISION = "f4a7b8c9d012"


def _config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _seed_phase3_graph(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(
        """
        INSERT INTO subscription_plans (
            id, code, display_name_en, display_name_fr, stripe_price_id,
            billing_interval, is_active, is_configured, created_at, updated_at
        ) VALUES (
            'plan-phase7', 'monthly-signals', 'Monthly signals',
            'Signaux mensuels', 'price_phase7', 'month', 1, 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO subscription_plans (
            id, code, display_name_en, display_name_fr, stripe_price_id,
            billing_interval, is_active, is_configured, created_at, updated_at
        ) VALUES (
            'plan-phase7-other', 'other-signals', 'Other signals',
            'Autres signaux', 'price_phase7_other', 'month', 1, 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO telegram_channels (
            id, code, telegram_chat_id, display_name_en, display_name_fr,
            is_active, is_configured, created_at, updated_at
        ) VALUES (
            'channel-phase7', 'signals', -1001234567890, 'Signals',
            'Signaux', 1, 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO telegram_channels (
            id, code, telegram_chat_id, display_name_en, display_name_fr,
            is_active, is_configured, created_at, updated_at
        ) VALUES (
            'channel-phase7-other', 'other-signals', -1009876543210, 'Other Signals',
            'Autres signaux', 1, 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO plan_channel_mappings (
            id, plan_id, channel_id, is_active, created_at, updated_at
        ) VALUES (
            'mapping-phase7', 'plan-phase7', 'channel-phase7', 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO plan_channel_mappings (
            id, plan_id, channel_id, is_active, created_at, updated_at
        ) VALUES (
            'mapping-phase7-other-plan', 'plan-phase7-other', 'channel-phase7', 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO plan_channel_mappings (
            id, plan_id, channel_id, is_active, created_at, updated_at
        ) VALUES (
            'mapping-phase7-other-channel', 'plan-phase7', 'channel-phase7-other', 1,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO subscribers (
            id, stripe_customer_id, stripe_email, normalized_email,
            created_at, updated_at
        ) VALUES (
            'subscriber-phase7', 'cus_phase7', 'phase7@example.com',
            'phase7@example.com',
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO subscriber_subscriptions (
            id, subscriber_id, plan_id, stripe_subscription_id, stripe_status,
            billing_status, current_period_start, current_period_end,
            cancel_at_period_end, created_at, updated_at
        ) VALUES (
            'subscription-phase7', 'subscriber-phase7', 'plan-phase7',
            'sub_phase7', 'active', 'active',
            '2026-07-27 12:00:00+00:00',
            '2026-08-27 12:00:00+00:00',
            0,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        INSERT INTO access_entitlements (
            id, subscriber_id, subscriber_subscription_id, plan_id, status,
            access_starts_at, paid_through_at, administratively_revoked,
            created_at, updated_at
        ) VALUES (
            'entitlement-phase7', 'subscriber-phase7', 'subscription-phase7',
            'plan-phase7', 'active',
            '2026-07-27 12:00:00+00:00',
            '2026-08-27 12:00:00+00:00',
            0,
            '2026-07-27 12:00:00+00:00',
            '2026-07-27 12:00:00+00:00'
        );
        """
    )
    connection.commit()


def test_phase7_fulfillment_migration_upgrade_downgrade_and_reupgrade(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "phase7-migration.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _config(database_url)

    command.upgrade(config, PHASE_6_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        _seed_phase3_graph(connection)
    finally:
        connection.close()

    command.upgrade(config, PHASE_7_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        table_sql = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'subscriber_access_fulfillments'
            """
        ).fetchone()[0]
        assert "subscriber_access_fulfillments" in tables
        assert "access_fulfillment_status" in table_sql
        assert "uq_access_fulfillment_entitlement_mapping" in table_sql
        assert "fk_access_fulfillment_entitlement_identity" in table_sql
        assert "fk_access_fulfillment_mapping_identity" in table_sql

        connection.execute(
            """
            INSERT INTO subscriber_access_fulfillments (
                id, subscriber_id, subscriber_subscription_id,
                access_entitlement_id, subscription_plan_id, telegram_channel_id,
                plan_channel_mapping_id, status, attempt_count,
                created_at, updated_at
            ) VALUES (
                'fulfillment-phase7', 'subscriber-phase7',
                'subscription-phase7', 'entitlement-phase7', 'plan-phase7',
                'channel-phase7', 'mapping-phase7', 'pending', 0,
                '2026-07-27 12:00:00+00:00',
                '2026-07-27 12:00:00+00:00'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    command.downgrade(config, PHASE_6_REVISION)
    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        retained_entitlement = connection.execute(
            "SELECT status FROM access_entitlements WHERE id = 'entitlement-phase7'"
        ).fetchone()
        alembic_revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
    finally:
        connection.close()

    assert "subscriber_access_fulfillments" not in tables
    assert retained_entitlement == ("active",)
    assert alembic_revision == PHASE_6_REVISION

    command.upgrade(config, "head")
    command.check(config)


def test_phase7_migration_enforces_constraints_independently(tmp_path, monkeypatch):
    database_path = tmp_path / "phase7-constraints.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = _config(database_url)
    command.upgrade(config, "head")

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        _seed_phase3_graph(connection)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_access_fulfillments (
                    id, subscriber_id, subscriber_subscription_id,
                    access_entitlement_id, subscription_plan_id,
                    telegram_channel_id, plan_channel_mapping_id, status,
                    attempt_count, created_at, updated_at
                ) VALUES (
                    'bad-status', 'subscriber-phase7', 'subscription-phase7',
                    'entitlement-phase7', 'plan-phase7', 'channel-phase7',
                    'mapping-phase7', 'not_a_status', 0,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_access_fulfillments (
                    id, subscriber_id, subscriber_subscription_id,
                    access_entitlement_id, subscription_plan_id,
                    telegram_channel_id, plan_channel_mapping_id, status,
                    attempt_count, created_at, updated_at
                ) VALUES (
                    'bad-mapping-plan', 'subscriber-phase7', 'subscription-phase7',
                    'entitlement-phase7', 'plan-phase7', 'channel-phase7',
                    'mapping-phase7-other-plan', 'pending', 0,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_access_fulfillments (
                    id, subscriber_id, subscriber_subscription_id,
                    access_entitlement_id, subscription_plan_id,
                    telegram_channel_id, plan_channel_mapping_id, status,
                    attempt_count, created_at, updated_at
                ) VALUES (
                    'bad-mapping-channel', 'subscriber-phase7', 'subscription-phase7',
                    'entitlement-phase7', 'plan-phase7', 'channel-phase7',
                    'mapping-phase7-other-channel', 'pending', 0,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_access_fulfillments (
                    id, subscriber_id, subscriber_subscription_id,
                    access_entitlement_id, subscription_plan_id,
                    telegram_channel_id, plan_channel_mapping_id, status,
                    attempt_count, created_at, updated_at
                ) VALUES (
                    'bad-fk', 'subscriber-phase7', 'subscription-phase7',
                    'missing-entitlement', 'plan-phase7', 'channel-phase7',
                    'mapping-phase7', 'pending', 0,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscriber_access_fulfillments (
                    id, subscriber_id, subscriber_subscription_id,
                    access_entitlement_id, subscription_plan_id,
                    telegram_channel_id, plan_channel_mapping_id, status,
                    attempt_count, created_at, updated_at
                ) VALUES (
                    'bad-attempts', 'subscriber-phase7', 'subscription-phase7',
                    'entitlement-phase7', 'plan-phase7', 'channel-phase7',
                    'mapping-phase7', 'pending', -1,
                    '2026-07-27 12:00:00+00:00',
                    '2026-07-27 12:00:00+00:00'
                )
                """
            )
        connection.rollback()
    finally:
        connection.close()
