import sqlite3

import pytest
from alembic import command
from test_phase7_migration import _config, _seed_phase3_graph


@pytest.mark.parametrize('acknowledged', [True, False])
def test_migration_only_removes_confirmed_deliveries_from_retry_queue(tmp_path, monkeypatch, acknowledged):
    path = tmp_path / 'onboarding.db'
    url = f'sqlite:///{path}'
    monkeypatch.setenv('DATABASE_URL', url)
    config = _config(url)
    command.upgrade(config, '6f8a2c4d9e10')
    with sqlite3.connect(path) as db:
        _seed_phase3_graph(db)
        db.execute('''
            INSERT INTO subscriber_access_fulfillments (
                id, subscriber_id, subscriber_subscription_id, access_entitlement_id,
                subscription_plan_id, telegram_channel_id, plan_channel_mapping_id,
                status, attempt_count, delivered_at, next_attempt_at, created_at, updated_at
            ) VALUES ('mail', 'subscriber-phase7', 'subscription-phase7', 'entitlement-phase7',
                      'plan-phase7', 'channel-phase7', 'mapping-phase7', 'retryable_failure', 1,
                      ?, '2026-07-27 12:05:00+00:00', '2026-07-27 12:00:00+00:00',
                      '2026-07-27 12:00:00+00:00')
        ''', ('2026-07-27 12:00:00+00:00' if acknowledged else None,))
    command.upgrade(config, 'head')
    command.check(config)
    with sqlite3.connect(path) as db:
        row = db.execute('SELECT status, delivered_at, next_attempt_at FROM subscriber_access_fulfillments').fetchone()
    assert row[0] == ('delivered' if acknowledged else 'retryable_failure')
    assert (row[1] is not None) == acknowledged
    assert (row[2] is None) == acknowledged
    command.downgrade(config, '6f8a2c4d9e10')
    command.upgrade(config, 'head')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT status, delivered_at, next_attempt_at FROM subscriber_access_fulfillments').fetchone() == row
