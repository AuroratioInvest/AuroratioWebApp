from datetime import datetime, timezone

from subscriber_models import (
    SignalDeliveryAttemptOutcome,
    SubscriberSignalDeliveryAttempt,
    SubscriberSignalPublication,
)


def test_phase9_delivery_attempt_model_defaults(db_session):
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    publication = SubscriberSignalPublication(
        id="publication-model",
        subscriber_signal_id="signal-model",
        signal_plan_target_id="target-model",
        plan_channel_mapping_id="mapping-model",
        subscription_plan_id="plan-model",
        telegram_channel_id="channel-model",
        created_at=now,
        updated_at=now,
    )
    attempt = SubscriberSignalDeliveryAttempt(
        id="attempt-model",
        publication=publication,
        attempt_number=1,
        processing_claim_id="claim-model",
        outcome=SignalDeliveryAttemptOutcome.processing,
        started_at=now,
        created_at=now,
    )

    assert attempt.publication is publication
    assert publication.delivery_attempts == [attempt]
    assert attempt.outcome == SignalDeliveryAttemptOutcome.processing
