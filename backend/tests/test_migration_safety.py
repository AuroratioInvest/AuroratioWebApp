import ast
import os
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"

PROTECTED_TABLES = {
    "users",
    "subscriptions",
    "broker_connections",
    "positions",
    "trade_log",
    "execution_logs",
}

PHASE_3_TABLES = {
    "subscription_plans",
    "telegram_channels",
    "plan_channel_mappings",
    "subscribers",
    "subscriber_subscriptions",
    "access_entitlements",
    "subscription_access_events",
    "integration_events",
    "audit_events",
}

PREVIOUS_REVISION = "29f6de39d824"

DESTRUCTIVE_OPERATIONS = {
    "drop_table",
    "drop_column",
    "drop_constraint",
    "rename_table",
    "execute",
}


def _upgrade_calls(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(), filename=str(path))
    upgrade = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "upgrade"
    )
    calls = []

    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "op":
            calls.append((node.func.attr, node.lineno))

    return calls


def test_migration_upgrades_do_not_contain_destructive_operations():
    violations = []

    for migration in sorted(VERSIONS_DIR.glob("*.py")):
        for operation, line in _upgrade_calls(migration):
            if (operation == "execute" and migration.name ==
                    "a7d3e9f102bc_reconcile_acknowledged_access_emails.py"):
                # One reviewed data repair, covered by migration round-trip
                # tests. Do not permit arbitrary SQL or legacy-table updates.
                tree = ast.parse(migration.read_text())
                call = next(node for node in ast.walk(tree)
                            if isinstance(node, ast.Call) and node.lineno == line)
                expected = ast.parse('''op.execute(sa.text("""
                    UPDATE subscriber_access_fulfillments
                    SET status = 'delivered', next_attempt_at = NULL,
                        delivery_claimed_at = NULL, processing_claim_id = NULL,
                        failed_at = NULL, last_error_code = NULL
                    WHERE delivered_at IS NOT NULL
                """))''', mode="eval").body
                # Normalize SQL whitespace only; every operation and predicate
                # must match the reviewed statement exactly.
                for expression in (call, expected):
                    for node in ast.walk(expression):
                        if isinstance(node, ast.Constant) and isinstance(node.value, str):
                            node.value = " ".join(node.value.split())
                assert ast.dump(call) == ast.dump(expected)
                continue
            if operation in DESTRUCTIVE_OPERATIONS:
                violations.append(f"{migration.name}:{line} op.{operation}")

    assert violations == [], (
        "Upgrade migrations must remain additive while legacy data is retained: "
        + ", ".join(violations)
    )


def test_upgrade_head_preserves_legacy_records_and_payment_data(tmp_path, monkeypatch):
    database_path = tmp_path / "migration-safety.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, PREVIOUS_REVISION)

    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            INSERT INTO users (
                id, email, hashed_password, membership_level, is_active,
                trading_enabled, preferred_trading_provider
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("legacy-user", "legacy@example.com", "hash", "classic", 1, 0, "disabled"),
        )
        connection.execute(
            """
            INSERT INTO subscriptions (
                id, user_id, stripe_customer_id, stripe_subscription_id, status
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("legacy-payment", "legacy-user", "cus_legacy", "sub_legacy", "active"),
        )
        connection.execute(
            """
            INSERT INTO broker_connections (
                id, user_id, broker_name, status, is_active,
                can_display_portfolio, can_execute_trades
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("legacy-broker", "legacy-user", "Legacy Broker", "active", 1, 1, 0),
        )
        connection.execute(
            """
            INSERT INTO positions (
                id, user_id, broker_connection_id, metal, etf_symbol, quantity
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("legacy-position", "legacy-user", "legacy-broker", "GOLD", "SGLN", 2),
        )
        connection.execute(
            """
            INSERT INTO trade_log (
                id, user_id, provider, sell_order_id, buy_order_id, status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-trade",
                "legacy-user",
                "ibkr_fa",
                "sell-order",
                "buy-order",
                "success",
            ),
        )
        connection.execute(
            """
            INSERT INTO execution_logs (
                id, user_id, provider, module_name, order_id, dry_run, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy-execution",
                "legacy-user",
                "ibkr_fa",
                "M1",
                "execution-order",
                0,
                "success",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    command.upgrade(config, "head")

    connection = sqlite3.connect(database_path)
    try:
        retained = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in PROTECTED_TABLES
        }
        order_data = connection.execute(
            "SELECT sell_order_id, buy_order_id FROM trade_log WHERE id = ?",
            ("legacy-trade",),
        ).fetchone()
        execution_order = connection.execute(
            "SELECT order_id FROM execution_logs WHERE id = ?",
            ("legacy-execution",),
        ).fetchone()
        tables_after_upgrade = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    finally:
        connection.close()

    assert retained == {table: 1 for table in PROTECTED_TABLES}
    assert order_data == ("sell-order", "buy-order")
    assert execution_order == ("execution-order",)
    assert PHASE_3_TABLES <= tables_after_upgrade

    command.downgrade(config, PREVIOUS_REVISION)

    connection = sqlite3.connect(database_path)
    try:
        tables_after_downgrade = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        retained_after_downgrade = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in PROTECTED_TABLES
        }
        identifiers_after_downgrade = {
            "user": connection.execute(
                "SELECT id, email FROM users WHERE id = 'legacy-user'"
            ).fetchone(),
            "payment": connection.execute(
                """
                SELECT id, stripe_customer_id, stripe_subscription_id
                FROM subscriptions WHERE id = 'legacy-payment'
                """
            ).fetchone(),
            "broker": connection.execute(
                "SELECT id FROM broker_connections WHERE id = 'legacy-broker'"
            ).fetchone(),
            "position": connection.execute(
                "SELECT id FROM positions WHERE id = 'legacy-position'"
            ).fetchone(),
            "trade": connection.execute(
                "SELECT id FROM trade_log WHERE id = 'legacy-trade'"
            ).fetchone(),
            "execution": connection.execute(
                "SELECT id FROM execution_logs WHERE id = 'legacy-execution'"
            ).fetchone(),
        }
    finally:
        connection.close()

    assert PHASE_3_TABLES.isdisjoint(tables_after_downgrade)
    assert retained_after_downgrade == {table: 1 for table in PROTECTED_TABLES}
    assert identifiers_after_downgrade == {
        "user": ("legacy-user", "legacy@example.com"),
        "payment": ("legacy-payment", "cus_legacy", "sub_legacy"),
        "broker": ("legacy-broker",),
        "position": ("legacy-position",),
        "trade": ("legacy-trade",),
        "execution": ("legacy-execution",),
    }

    command.upgrade(config, "head")
    command.check(config)


def test_phase3_migration_enforces_identity_and_identifier_constraints(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "phase3-constraints.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    command.check(config)

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        schema_sql = "\n".join(
            row[0]
            for row in connection.execute(
                """
                SELECT sql FROM sqlite_master
                WHERE type = 'table' AND name IN (
                    'subscription_plans',
                    'telegram_channels',
                    'subscribers',
                    'subscriber_subscriptions',
                    'access_entitlements',
                    'subscription_access_events',
                    'integration_events'
                )
                """
            )
            if row[0]
        )
        for constraint_name in {
            "ck_subscription_plan_code_nonempty",
            "ck_subscription_plan_stripe_price_id_nonempty",
            "ck_telegram_channel_code_nonempty",
            "ck_subscriber_stripe_customer_id_nonempty",
            "ck_subscriber_normalized_email_nonempty",
            "ck_subscriber_subscription_stripe_id_nonempty",
            "ck_integration_event_external_id_nonempty",
            "fk_access_entitlement_subscription_identity",
            "fk_access_event_subscription_owner",
            "fk_access_event_entitlement_identity",
            "ck_access_event_entitlement_requires_subscription",
            "uq_access_entitlement_subscription",
        }:
            assert constraint_name in schema_sql

        connection.execute(
            """
            INSERT INTO subscription_plans (
                id, code, display_name_en, display_name_fr,
                is_active, is_configured, created_at, updated_at
            ) VALUES
                ('plan-a', 'plan-a', 'Plan A', 'Plan A', 1, 1, ?, ?),
                ('plan-b', 'plan-b', 'Plan B', 'Plan B', 1, 1, ?, ?)
            """,
            ("2026-07-27T12:00:00+00:00",) * 4,
        )
        connection.execute(
            """
            INSERT INTO subscribers (
                id, stripe_customer_id, created_at, updated_at
            ) VALUES
                ('subscriber-a', 'cus_a', ?, ?),
                ('subscriber-b', 'cus_b', ?, ?)
            """,
            ("2026-07-27T12:00:00+00:00",) * 4,
        )
        connection.execute(
            """
            INSERT INTO subscriber_subscriptions (
                id, subscriber_id, plan_id, stripe_subscription_id,
                billing_status, cancel_at_period_end, created_at, updated_at
            ) VALUES (
                'subscription-a', 'subscriber-a', 'plan-a', 'sub_a',
                'active', 0, ?, ?
            )
            """,
            ("2026-07-27T12:00:00+00:00",) * 2,
        )
        connection.commit()

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO access_entitlements (
                    id, subscriber_id, subscriber_subscription_id, plan_id,
                    status, administratively_revoked, created_at, updated_at
                ) VALUES (
                    'bad-entitlement', 'subscriber-b', 'subscription-a', 'plan-b',
                    'pending', 0, ?, ?
                )
                """,
                ("2026-07-27T12:00:00+00:00",) * 2,
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO subscribers (
                    id, stripe_customer_id, created_at, updated_at
                ) VALUES ('empty-customer', '   ', ?, ?)
                """,
                ("2026-07-27T12:00:00+00:00",) * 2,
            )
    finally:
        connection.close()

    command.downgrade(config, PREVIOUS_REVISION)
    command.upgrade(config, "head")
    command.check(config)
