# Accountless billing configuration

Phase 6 uses Stripe-hosted Checkout and Customer Portal pages. Stripe webhooks
remain authoritative for creating subscribers, synchronizing billing state, and
granting or changing access entitlements.

## Required configuration

- `STRIPE_SECRET_KEY`: server-side Stripe API key.
- `STRIPE_WEBHOOK_SECRET`: signature secret used by the existing webhook.
- `STRIPE_MONTHLY_SIGNAL_PRICE_ID`: existing recurring Stripe Price for the
  public €14.99 monthly subscription. Public accountless Checkout uses this
  value; the browser never supplies a Stripe Price ID.
- `MONTHLY_SIGNAL_PLAN_CODE`: local plan code; defaults to
  `monthly-signals`.
- `PUBLIC_APP_URL`: trusted browser origin required to build Checkout success
  and cancellation URLs, Portal return URLs, and emailed one-time-link URLs.
  HTTPS is required except on localhost.
- `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`, and `BREVO_SENDER_NAME`:
  transactional delivery for billing-management links.

Optional:

- `STRIPE_BILLING_PORTAL_CONFIGURATION_ID`: an existing Stripe Portal
  configuration. Portal business settings are not changed by the application.
- `PORTAL_ACCESS_TOKEN_TTL_MINUTES`: one-time link lifetime, 15 minutes by
  default and capped at 60 minutes.
- `PORTAL_LINK_COOLDOWN_MINUTES`: database-backed issuance cooldown for each
  eligible Stripe Customer relationship, 5 minutes by default.
- `PORTAL_REQUEST_MIN_RESPONSE_MS`: minimum generic request duration used to
  reduce email-enumeration timing differences.

No Stripe product, Stripe Price, or Portal configuration is created
dynamically. On startup, when `STRIPE_MONTHLY_SIGNAL_PRICE_ID` and
`MONTHLY_SIGNAL_PLAN_CODE` are valid and the configured plan code is missing
locally, the backend bootstraps one active, configured, non-archived
`subscription_plans` row by mirroring that trusted environment configuration
into the database. Existing plan rows are never overwritten, re-enabled,
unarchived, or silently repaired; if an existing row is inactive, archived, or
price-mismatched, Checkout still fails closed until an operator corrects the
local configuration. Configuration should be performed separately for each
Stripe test or live environment.

## Public endpoints and routes

- `POST /public/billing/checkout-session`
- `POST /public/billing/portal-link`
- `POST /public/billing/portal-session`
- `/subscription/success`
- `/subscription/cancelled`
- `/manage-subscription`
- `/manage-subscription/access`

Checkout redirects never create local access. Only a verified Stripe webhook
can synchronize `Subscriber`, `SubscriberSubscription`, and
`AccessEntitlement`.

Portal-link requests always return the same generic `202` response after the
configured minimum local processing duration. Subscriber resolution joins
`SubscriberSubscription` to `Subscriber`; an email-matching subscriber without
a real Stripe subscription is not eligible. Eligible subscriptions are ordered
deterministically:

1. active or trialing subscriptions that are not scheduled to cancel;
2. delinquent, past-due, unpaid, or incomplete subscriptions;
3. subscriptions scheduled to cancel whose current period has not ended;
4. cancelled and other historical subscriptions.

Ties use current-period end, local subscription creation time, and the stable
local subscription ID. `Subscriber.updated_at` is never a selector.

Results are deduplicated by Stripe Customer ID. Each distinct eligible customer
gets its own purpose-bound token with the trusted Stripe Customer ID frozen on
the token row at issuance. Exchange uses this frozen value, never a browser
value or the subscriber row's later mutable value, and rejects the token if that
frozen customer no longer has a trusted local subscription relationship. One
verification email contains all resulting links, labeled with only the
localized plan name, billing-state context, and period date. Stripe Customer and
Subscription IDs are never included. Multiple local subscriptions for one
Stripe Customer produce one link using the highest-priority subscription as
descriptive context.

The `portal_link_issuances` row for each subscriber is claimed with a
database-native upsert whose conditional update succeeds only after
`next_allowed_at`. This is the cross-worker and cross-instance cooldown
boundary. The in-memory IP limiter is only a per-process abuse-control layer;
deployments behind a reverse proxy must ensure the application receives a
trusted client address without blindly accepting spoofable forwarding headers.
Concurrent requests during a cooldown can issue at most one token for each
subscriber relationship.

When a new token is issued, previous queued, unclaimed, unconsumed tokens for
that relationship are invalidated. Claimed or delivered links remain valid
until expiry or consumption; failed links are invalidated; consumed links remain
terminal. Expired unconsumed Portal tokens are opportunistically invalidated
during later Portal-link requests; retained rows preserve audit history and can
be archived under a future approved retention policy.

The database transaction commits tokens and cooldown claims before delivery.
FastAPI `BackgroundTasks` then opens a fresh database session, claims only
currently valid unclaimed tokens, and sends the remaining links in one Brevo
message outside the awaited public request handler. Stale, consumed, expired,
invalidated, or customer-mismatched tokens are skipped before any email is
sent. This removes Brevo latency as a direct email-enumeration oracle. The
dispatcher is process-local and is **not a durable queue**: a process crash
after commit but before task execution can lose that delivery. Production
therefore depends on correct Brevo configuration and should move dispatch to a
durable worker before stronger delivery guarantees are advertised. A definitive
delivery failure invalidates only the claimed batch and records safe audit
outcomes. Duplicate task execution cannot send the same token batch twice
because already claimed or delivered tokens are not claimable again. Raw tokens
and full links are never written to the database, logs, or audit metadata.

The browser receives a raw token only through the emailed URL fragment, removes
that fragment before exchange, and submits the token server-side. A token is
short-lived, purpose-bound, single-use, and atomically claimed. Stripe provider
failure rolls the claim back so the same unexpired link can be retried.

SQLite exercises the conditional cooldown upsert in automated tests. Before
production, run the concurrent issuance and token-consumption scenarios against
the live PostgreSQL version and confirm proxy/client-IP behavior in the deployed
topology.

## Phase 7 private-channel access fulfillment

Stripe webhooks remain authoritative only for local subscription and entitlement
synchronization. When an accountless entitlement becomes access-granting, the
webhook transaction creates durable `subscriber_access_fulfillments` rows for
each active plan-to-channel mapping. It does not call Telegram or Brevo.

Fulfillment is processed separately through the access-fulfillment CLI worker.
An external trusted scheduler should call it periodically with a bounded
`--limit`; FastAPI does not start an automatic fulfillment scheduler or worker.
Because provider calls are synchronous, each invocation processes at most two
due fulfillment records. Use `--limit 1` when provider latency is high and call
the command repeatedly for larger queues:

```bash
python -m backend.commands.process_access_fulfillments --limit 1
```
Each fulfillment record represents one entitlement and one configured private
channel. Processing claims a row with a conditional database update, creates a
one-member invite that expires after the configured TTL, sends provider-neutral
access instructions by email, and then marks the row delivered only after the
email provider accepts the message.

Required private-channel configuration:

- `TELEGRAM_BOT_TOKEN`: server-side bot token. Never expose this to the browser.
- `TELEGRAM_API_BASE_URL`: defaults to `https://api.telegram.org`.
- `TELEGRAM_INVITE_TTL_HOURS`: invite lifetime, 24 hours by default.
- `TELEGRAM_PROVIDER_TIMEOUT_SECONDS`: strict provider timeout.
- `ACCESS_FULFILLMENT_MAX_ATTEMPTS`: bounded retry attempts.
- `ACCESS_FULFILLMENT_RETRY_SECONDS`: retry delay for transient failures.
- `ACCESS_FULFILLMENT_CLAIM_LEASE_SECONDS`: stale processing-claim recovery.

Telegram setup requirements from the official Bot API:

- create the private broadcast channel before launch;
- add the bot as an administrator of that channel;
- grant the bot permission to invite users;
- use additional invite links created by the bot;
- `member_limit=1` is used for single-use invitations;
- `expire_date` is sent as a Unix timestamp;
- failed email delivery triggers an attempted `revokeChatInviteLink` call before
  retrying with a fresh invitation.

The raw invitation URL exists only in worker memory until email delivery
finishes. The database stores a non-secret provider reference, expiry time,
status, attempt metadata, and sanitized error codes. Audit records do not store
bot tokens, raw invite URLs, complete invite-link tokens, Stripe Customer IDs,
or provider response bodies.

If Telegram invite creation succeeds but Brevo delivery fails, the worker
attempts to revoke the invite, records a retryable failure, and retries later
with a new invite. If the entitlement becomes inactive before fulfillment
completes, pending/undelivered fulfillment is cancelled and no invitation is
sent. Phase 7 does **not** remove already joined channel members; cancellation
and expired-access removal require a later reconciliation phase.

Existing active entitlements can be enqueued with the protected admin backfill
endpoint. The backfill is idempotent: it creates only missing records and does
not regenerate delivered invitations automatically. Backfill is bounded and
ordered by entitlement ID. Use `limit` plus the returned `next_cursor` as
`after_entitlement_id` to process repeated batches; when an `entitlement_id` is
provided, only that entitlement is checked.

Fulfillment delivery is at-least-once around external providers. If Brevo
accepts an email and the process crashes before the delivered state is recorded,
a later retry can send a fresh invitation. Invitations remain single-use and
short-lived, and raw invitation URLs are not persisted.

## Phase 8 admin-approved signal publication

Subscriber trading signals use a separate accountless domain and do not reuse
the legacy customer trading application, broker execution, or legacy signal
routes. An authenticated active administrator creates a structured signal draft,
targets one or more configured subscription plans, and explicitly approves the
draft. Approval changes the signal to `approved`, creates durable
`subscriber_signal_publications` rows for each active plan-to-channel mapping,
and writes audit records in the same database transaction. Provider calls never
run during approval.

Publication is by active plan/channel mapping, not by individual subscriber.
Inactive plans, inactive mappings, inactive/unconfigured channels, and archived
records are skipped. If an approved signal currently has no eligible mappings,
the approval remains durably observable through audit records and the bounded
backfill endpoint can enqueue publication rows later after configuration is
corrected.

Operational endpoints:

- `POST /admin/subscriber-signals` creates a draft.
- `PATCH /admin/subscriber-signals/{signal_id}` updates a draft before approval.
- `POST /admin/subscriber-signals/{signal_id}/approve` approves and enqueues.
- `POST /admin/subscriber-signals/{signal_id}/cancel` cancels an unpublished
  draft or undelivered publications for an approved signal.
- `GET /admin/subscriber-signals` lists signals with bounded pagination.
- `GET /admin/signal-publications` lists publication state with bounded
  pagination.
- `POST /admin/signal-publications/{publication_id}/retry` resets a failed
  non-published publication for retry when the signal is still eligible.
- `POST /admin/signal-publications/backfill` checks approved signals in bounded,
  deterministic batches and creates missing publication rows. Dry-run mode is
  write-free.
- `POST /admin/signal-publications/process-due` processes due publication work
  for authenticated manual recovery.

Production automation should use the CLI worker rather than the admin HTTP
endpoint:

```bash
python -m backend.commands.process_signal_publications --limit 1
```

The worker performs one bounded pass per invocation, calls the durable
publication service directly, and does not poll or call HTTP. A trusted external
scheduler should invoke it repeatedly, initially once per minute. The admin HTTP
endpoint remains available for manual recovery. Do not run either scheduler or
worker inside FastAPI web workers. The service is synchronous and bounded: the
default limit is 1 and the maximum limit is 2 publication records per request.
Use `--limit 1` when provider latency is high.

Publication states are `pending`, `processing`, `published`,
`retryable_failure`, `terminal_failure`, and `cancelled`. A worker claims one
due row using a conditional database update and an unpredictable claim ID.
Final state updates predicate on that claim ID, so a stale worker cannot
finalize after another worker recovers the job. Retryable failures use bounded
attempt counts, `SIGNAL_PUBLICATION_RETRY_SECONDS`, and
`SIGNAL_PUBLICATION_CLAIM_LEASE_SECONDS`; terminal failures require an explicit
admin retry. Publication delivery is at-least-once around the provider-success
and database-finalization crash window.

Provider messages are rendered from structured canonical signal fields. They
contain no subscriber personal data, Stripe identifiers, internal database IDs,
or broker-execution wording. They remind recipients that the signal is
informational and that trading decisions and order placement remain manual.

Additional Phase 8 configuration:

- `SIGNAL_PUBLICATION_MAX_ATTEMPTS`: maximum publication attempts.
- `SIGNAL_PUBLICATION_RETRY_SECONDS`: retry delay for transient provider
  failures.
- `SIGNAL_PUBLICATION_CLAIM_LEASE_SECONDS`: stale processing-claim recovery
  window.

Phase 8 does not remove channel members, edit or delete already-published
provider messages, or execute trades.

## Automatic precious-metals strategy bridge

The accountless launch product uses the existing root-level precious-metals
strategy as the authoritative calculation path. The active root files are:

- `scheduler.py`: weekday 17:05 CET/host-time orchestration. In legacy mode it
  still runs the broker-execution cycle. With `LEGACY_CUSTOMER_APP_ENABLED=false`
  it runs the subscriber signal cycle instead.
- `market_data.py`: provider-neutral normalized market observations. The
  current development adapter preserves the existing Yahoo Finance retrieval
  path; production data-source suitability, licensing, and coverage must be
  verified before launch.
- `ratios.py`: authoritative AU/AG, AU/PT, and AU/PD ratio formulas.
- `state.py`: authoritative hysteresis counters and two-consecutive-trading-day
  confirmation rule.
- `data/prices_clean.csv`: local ratio-history input used by the root strategy.
- `strategy_decisions.py`: structured decision boundary around the existing
  ratio and state logic. It does not know subscribers, private channels, or
  provider identifiers.

Legacy/operational files that are not part of the accountless signal bridge:

- `broker.py` and `broker_single_module_backup.txt`: legacy Interactive Brokers
  execution; not called by the subscriber signal cycle.
- `backend/services/website_strategy_service.py` and
  `backend/services/website_execution_service.py`: legacy customer-app strategy
  and execution services; not used to publish accountless subscriber signals.
- `backend/routers/signals.py`: legacy/customer-facing signal route; not part
  of the accountless subscriber publication path.

The automatic bridge is intentionally server-side only. No public or admin
request can submit a payload that impersonates a strategy result. When the root
strategy confirms a decision, `services.strategy_signal_bridge_service` maps the
trusted structured decision to canonical `subscriber_signals`, derives target
plans from trusted configuration, marks the signal approved as a system action,
creates relational plan targets, enqueues durable publication rows through the
existing publication service, and writes audit records in one database
transaction. Provider calls do not occur inside that transaction.

Trusted automatic signal configuration:

- `SUBSCRIBER_SIGNAL_PLAN_CODES`: comma-separated active configured plan codes
  that receive automatic strategy signals. Defaults to `MONTHLY_SIGNAL_PLAN_CODE`
  and then `monthly-signals`.
- `MARKET_DATA_MAX_AGE_DAYS`: maximum allowed market-observation age. Defaults
  to 4 calendar days to tolerate weekend data around a weekday run while still
  rejecting stale inputs.

Market observations must include gold, silver, platinum, palladium, and USD/CHF
with positive values, compatible units/currencies, timezone-aware source
timestamps, and matching metal source dates. Missing, stale, partial,
non-positive, incompatible, or malformed data skips signal generation rather
than fabricating a price or carrying one forward silently.

Strategy decisions are idempotent. The subscriber signal table stores a durable
strategy identity derived from the stable strategy identifier, strategy version,
ratio identifier, decision date, and decision type. Re-running the scheduler,
catch-up, or integration retry for the same decision returns the existing signal
and does not create duplicate publications. A duplicate identity with different
canonical signal content fails visibly.

The normal production invocation is one trusted external scheduler calling:

```bash
python scheduler.py --now
```

at 17:05 in the configured business timezone, or running `python scheduler.py`
as a single external scheduler process. The root scheduler now runs only the
accountless subscriber signal cycle; it does not call broker, portfolio, order,
or legacy customer execution paths. Do not start this scheduler inside every web
worker. After strategy decisions are enqueued, durable delivery still requires
the existing publication processor. A trusted external scheduler should invoke
the worker repeatedly, initially once per minute:

```bash
python -m backend.commands.process_signal_publications --limit 1
```

The admin `POST /admin/signal-publications/process-due` endpoint remains for
manual recovery only. Queued publication rows do not deliver themselves
automatically.

For local or test-mode operational validation, create a controlled non-trading
test signal without a legacy admin account:

```bash
python -m backend.commands.create_test_signal --plan-code monthly-signals
```

The command refuses to run when `ENV=production` or `APP_ENV=production`, uses
the same backend database configuration, creates a clearly labeled approved
test signal through the subscriber signal service layer, and enqueues durable
publication work only through configured plan-to-channel mappings. It does not
call the private-channel provider directly; deliver the queued row with the
publication worker command above. Re-running the command with the same
`--test-id` is idempotent. Use `--dry-run` to validate configuration without
writing.
