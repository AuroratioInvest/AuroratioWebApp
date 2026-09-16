"""Exercise real Stripe ingestion, durable fulfillment, and repeated backfills."""
import asyncio
from datetime import timedelta

import pytest

from services.stripe_subscription_service import process_verified_stripe_event
from services.subscriber_fulfillment_service import (
    enqueue_fulfillment_for_entitlement,
    enqueue_missing_fulfillments_for_active_entitlements,
    process_due_fulfillments,
    request_manual_fulfillment_retry,
)
from subscriber_models import AccessEntitlement, AccessFulfillmentStatus, SubscriberAccessFulfillment
from test_phase7_fulfillment import (
    NOW, FakeTelegramService, _plan, _channel, _mapping, _session_factory, _subscriber_stack,
)
from test_stripe_subscription_service import _event, _payload, _subscription_object


@pytest.mark.parametrize('activation_type', [
    'checkout.session.completed', 'customer.subscription.created', 'invoice.paid',
    'invoice.payment_succeeded', 'customer.subscription.updated',
])
@pytest.mark.parametrize('fail_initial', [False, True])
def test_activation_renewals_replays_and_backfills(db_session, activation_type, fail_initial):
    plan = _plan(db_session)
    _mapping(db_session, plan, _channel(db_session))
    provider = FakeTelegramService()
    attempts = []
    successes = []
    snapshot = _subscription_object(price_id=plan.stripe_price_id,
                                    period_start=NOW, period_end=NOW + timedelta(days=30))

    async def email(**kwargs):
        attempts.append(kwargs)
        if fail_initial and len(attempts) == 1:
            return False
        successes.append(kwargs)
        return True

    def ingest(kind, identifier, now):
        if kind == 'checkout.session.completed':
            obj = {'id': 'cs_onboarding', 'mode': 'subscription', 'subscription': snapshot['id']}
        elif kind.startswith('invoice.'):
            obj = {'id': 'in_onboarding', 'subscription': snapshot['id']}
        else:
            obj = snapshot
        event = _event(event_type=kind, event_id=identifier, created_at=now, data_object=obj)
        outcome = process_verified_stripe_event(db_session, event=event, payload=_payload(event),
                                               now=now, retrieve_subscription=lambda _: snapshot)
        assert not outcome.retryable
        assert outcome.status.value == 'processed'
        return outcome

    def work(now):
        return asyncio.run(process_due_fulfillments(
            session_factory=_session_factory(db_session), telegram_service=provider,
            email_sender=email, now=now))

    ingest(activation_type, 'evt_activation', NOW)
    work(NOW)
    db_session.expire_all()
    row = db_session.query(SubscriberAccessFulfillment).one()
    assert (row.delivered_at is None) == fail_initial
    assert ingest(activation_type, 'evt_activation', NOW).duplicate
    if fail_initial:
        assert work(NOW).processed == 0
        assert work(NOW + timedelta(minutes=6)).delivered == 1
    assert len(successes) == 1
    db_session.refresh(row)
    sent_at = row.delivered_at

    for period in range(1, 4):
        now = NOW + timedelta(days=30 * period)
        end = now + timedelta(days=30)
        snapshot['current_period_start'] = int(now.timestamp())
        snapshot['current_period_end'] = int(end.timestamp())
        for kind in ('invoice.paid', 'invoice.payment_succeeded', 'customer.subscription.updated'):
            identifier = f'evt_{period}_{kind}'
            ingest(kind, identifier, now)
            assert ingest(kind, identifier, now).duplicate
            assert work(now).processed == 0
        for _ in range(3):
            assert enqueue_missing_fulfillments_for_active_entitlements(
                db_session, now=now)['created'] == 0
            assert work(now).processed == 0
        db_session.expire_all()
        assert db_session.query(AccessEntitlement).one().paid_through_at == end
        assert db_session.query(SubscriberAccessFulfillment).one().delivered_at == sent_at
    assert len(successes) == 1
    assert len(attempts) == 1 + int(fail_initial)


@pytest.mark.parametrize('status', [AccessFulfillmentStatus.pending,
                                   AccessFulfillmentStatus.retryable_failure,
                                   AccessFulfillmentStatus.cancelled,
                                   AccessFulfillmentStatus.processing])
def test_persisted_acknowledgement_prevents_resend_even_if_status_changed(db_session, status):
    plan = _plan(db_session)
    _mapping(db_session, plan, _channel(db_session))
    _, _, entitlement = _subscriber_stack(db_session, plan)
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    db_session.commit()
    row = db_session.query(SubscriberAccessFulfillment).one()
    row.status = status
    row.delivered_at = NOW
    row.delivery_claimed_at = NOW
    db_session.commit()
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    request_manual_fulfillment_retry(db_session, fulfillment_id=row.id,
                                    admin_user_id='unused', now=NOW + timedelta(hours=1))
    provider = FakeTelegramService()
    result = asyncio.run(process_due_fulfillments(
        session_factory=_session_factory(db_session), telegram_service=provider,
        now=NOW + timedelta(hours=1)))
    assert result.processed == 0
    assert provider.created == []


def test_manual_retry_cannot_steal_live_delivery_claim(db_session):
    plan = _plan(db_session)
    _mapping(db_session, plan, _channel(db_session))
    _, _, entitlement = _subscriber_stack(db_session, plan)
    enqueue_fulfillment_for_entitlement(db_session, entitlement=entitlement, now=NOW)
    db_session.commit()
    row = db_session.query(SubscriberAccessFulfillment).one()
    row.status = AccessFulfillmentStatus.processing
    row.processing_claim_id = 'live-worker'
    row.delivery_claimed_at = NOW
    db_session.commit()
    request_manual_fulfillment_retry(db_session, fulfillment_id=row.id,
                                    admin_user_id='unused', now=NOW + timedelta(seconds=1))
    assert row.status == AccessFulfillmentStatus.processing
    assert row.processing_claim_id == 'live-worker'


def test_stale_worker_cannot_take_claim_during_provider_acceptance(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.exc import OperationalError
    from sqlalchemy.orm import sessionmaker
    from database import Base, configure_sqlite_foreign_keys
    from services.subscriber_fulfillment_service import _claim_one_due_fulfillment

    engine = create_engine(f'sqlite:///{tmp_path / "concurrent.db"}',
                           connect_args={'timeout': 0.05})
    configure_sqlite_foreign_keys(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    db = factory()
    try:
        plan = _plan(db)
        _mapping(db, plan, _channel(db))
        _, _, entitlement = _subscriber_stack(db, plan)
        enqueue_fulfillment_for_entitlement(db, entitlement=entitlement, now=NOW)
        db.commit()
        sent = []

        async def email(**kwargs):
            # A separate connection tries to reclaim the lease while the first
            # worker is waiting for the provider. The write lock must cover it.
            rival = factory()
            try:
                with pytest.raises(OperationalError, match='locked'):
                    _claim_one_due_fulfillment(rival, now=NOW + timedelta(hours=1))
            finally:
                rival.close()
            sent.append(kwargs)
            return True

        result = asyncio.run(process_due_fulfillments(
            session_factory=factory, telegram_service=FakeTelegramService(),
            email_sender=email, now=NOW))
        assert result.delivered == 1
        assert len(sent) == 1
        assert asyncio.run(process_due_fulfillments(
            session_factory=factory, telegram_service=FakeTelegramService(),
            email_sender=email, now=NOW + timedelta(hours=1))).processed == 0
    finally:
        db.close()
        engine.dispose()
