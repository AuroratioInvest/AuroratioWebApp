# Telegram onboarding email investigation

## Findings

The reported renewal-triggered resend is **not reproduced by the current checkout's ordinary lifecycle**. No production Stripe events, Brevo delivery logs, deployed revision, or external scheduler configuration were available in this investigation. The specific production event remains unconfirmed.

Confirmed defects in the delivery path were repaired:

- Delivery released its row lock before calling the email provider and opened another transaction to save success. An expired lease or administrator retry could replace the claim during that interval. The first worker could send successfully but lose ownership before acknowledging delivery; another worker could then send again.
- An administrator retry could reset a live processing claim.
- Retry eligibility used mutable status without consulting the existing `delivered_at` acknowledgement. A status reset could therefore re-enable an already acknowledged email.
- The email transport treated redirects as success. Only HTTP 2xx responses now count as provider acceptance.

These are confirmed code weaknesses, not proof that they caused the reported production incident.

## Complete path inventory

| Path | Responsibility and email behavior |
| --- | --- |
| `backend/routers/stripe_router.py:stripe_webhook` | Verifies Stripe events and calls durable ingestion. Checkout completion, subscription created/updated, and both invoice success events schedule one background fulfillment pass. No direct email call. |
| `backend/services/stripe_subscription_service.py:process_verified_stripe_event` | Persists unique Stripe event identity, serializes processing, and skips completed event replays. |
| `backend/services/stripe_subscription_service.py:synchronize_stripe_subscription` | Retrieves current subscription state; updates the existing subscription and entitlement; enqueues fulfillment on meaningful changes, including period extension. Enqueue reuses the unique entitlement/mapping record. |
| `backend/services/stripe_subscription_service.py:replay_stripe_integration_event` | Administrator recovery uses the same durable ingestion path. No independent email sender. |
| `backend/services/subscriber_fulfillment_service.py:enqueue_fulfillment_for_entitlement` | Queues initial access and retains existing delivery acknowledgement. Cancels undelivered work when access ends. |
| `backend/services/subscriber_fulfillment_service.py:enqueue_missing_fulfillments_for_active_entitlements` | Bounded backfill/reconciliation of missing access invitations. Repeated passes reuse existing records. |
| `backend/services/subscriber_fulfillment_service.py:process_one_fulfillment` | The sole production caller of the private-access email function, through an injectable sender. Creates an invite and acknowledges it only after provider acceptance. |
| `backend/services/email_service.py:send_private_access_instructions` → `send_email` | Builds the bilingual subscription-active/private-channel invitation and sends through Brevo. Other email functions send billing-management links, verification codes, password resets, or contact messages; they do not send Telegram onboarding links. |
| `backend/commands/process_access_fulfillments.py` | Periodic worker entry point; processes existing durable work. It does not synchronize Stripe subscriptions. |
| `backend/routers/admin_fulfillment.py` | Manual due processing, retry, and backfill all use the same service. |
| `backend/main.py:startup` | Bootstraps configured plan/channel mappings. No email or subscription synchronization. |
| `scheduler.py` | Market-data and signal pipeline; no subscription onboarding email. |
| `backend/services/website_execution_scheduler.py` | Legacy trading execution scheduler; no subscription onboarding email. |
| `backend/services/telegram_membership_service.py` | Membership binding/removal and entitlement checks; no onboarding email. |

No nightly Stripe subscription synchronization job was found in this repository. Repeated reconciliation was tested through its actual synchronization service and backfill functions. Any externally configured nightly job must be checked against the deployed code.

No sandbox recipient override was found here. The sender still uses the subscriber's Stripe email, falling back to normalized email. No recipient routing or provider-side sandbox settings were changed. Idempotency is keyed by the durable entitlement/channel mapping, not recipient email; two distinct subscriptions sharing a test recipient still each receive their initial invitation.

## Behavior after the change

- First access grant queues a single durable fulfillment per entitlement/channel mapping.
- Provider acceptance sets `subscriber_access_fulfillments.delivered_at` and terminal delivered status in the same locked transaction. This existing column is the equivalent of `telegram_link_sent_at`; a second timestamp would be redundant.
- Period extensions and invoice success events preserve access and reuse the acknowledged fulfillment without another onboarding send.
- Known failed email attempts retain a null acknowledgement and use existing retry delays, attempt limits, and invite revocation behavior.
- Duplicate webhook IDs remain deduplicated by the existing integration-event records. Distinct events and repeated worker/backfill runs share the persistent fulfillment guard.
- Cancellation, expiration, grace periods, access removal, and access grants are unchanged. A separate subscription or newly mapped channel still has its own onboarding lifecycle.

## Migration and deployment

1. Pause access-fulfillment workers and drain webhook/background work so old and new delivery code do not overlap.
2. Against the intended deployment database, run from `backend`: `alembic upgrade head` (using the deployment virtual environment).
3. Deploy/restart the API and all access-fulfillment workers, then resume processing.

Revision `a7d3e9f102bc` follows `6f8a2c4d9e10`. It reuses the existing schema and reconciles rows that already have `delivered_at`: sets delivered status and clears retry/claim/error fields. It does not infer delivery from payment state, invent timestamps, or alter access/payment records. Downgrade deliberately retains acknowledgements. Migration round-trip and legacy-data preservation tests cover this repair; the migration safety test permits only the exact reviewed UPDATE.

## Verification

137 tests passed across:

- `test_onboarding_email_idempotency.py`
- `test_onboarding_email_migration.py`
- `test_phase7_fulfillment.py`
- `test_stripe_router.py`
- `test_stripe_subscription_service.py`
- `test_email_service.py`
- `test_access_fulfillment_worker_command.py`
- `test_phase7_migration.py`
- `test_migration_safety.py`

Coverage includes all five activation event types, initial-send failure and retry, exact webhook replays, three renewal periods with both invoice success events and subscription updates, repeated reconciliation/backfills, persisted acknowledgements with changed statuses, manual claim protection, and a separate SQLite connection attempting lease takeover during delivery. Existing subscription tests cover cancellation/expiration and grace rules. Five existing FastAPI/Starlette deprecation warnings remain.

### Full-suite run before committing

- Backend: `.venv/bin/python -m pytest backend/tests -q` — 347 passed, 2 failed.
- Frontend: `npm test` from `frontend` — 38 passed, 1 failed.
- Both backend failures are in `test_market_data_api.py`: `test_scheduler_startup_refresh_fetches_validates_and_persists_idempotently` and `test_scheduler_market_write_failure_does_not_interrupt_signal_workflow`. Their fixed August 13, 2026 observations fail the current-date freshness check.
- The frontend failure is `success and cancellation routes are honest and accountless`, which expects checkout copy no longer present in the page.
- All three failures were reproduced from isolated archives of unchanged `main`. They were left unchanged to keep this commit limited to Telegram email idempotency. All Telegram email tests passed in the full run.

## Remaining limits and incident follow-up

- HTTP 2xx means provider acceptance, not confirmed inbox delivery. No provider delivery callback is configured by this change.
- A process crash or lost response after provider acceptance but before database commit remains an ambiguous outcome. Database-only idempotency cannot guarantee exactly one external email in this case; provider-supported deduplication/reconciliation would be needed. This change prevents ordinary renewal/replay resends and concurrent claim takeover, but does not claim crash-proof exactly-once delivery.
- Lock contention was exercised using independent SQLite connections. PostgreSQL row locks are used by the production code path, but were not exercised against a live PostgreSQL instance.
- Holding the lock through the email call can delay competing operations for the provider request duration (the existing HTTP timeout is 15 seconds).
- To attribute the actual incident, correlate the deployed revision, Stripe subscription and event IDs, `integration_events`, `subscription_access_events`, fulfillment IDs/status/timestamps, `access_fulfillment_*` audit events, and Brevo acceptance timestamps. Determine whether the duplicate was a second attempt on the same fulfillment or initial delivery for another subscription sharing a sandbox recipient. Check external cron jobs and provider recipient overrides as well.
