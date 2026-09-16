# AuroRatio production-readiness audit

Date: September 15, 2026. Branch: `fix/telegram-email-idempotency`.

## Scope and result

**Not ready for an unattended paid launch yet.** This is a repository-backed audit, not an inspection of the Railway dashboard, PostgreSQL contents, DNS, provider settings or credentials. The expired Railway trial and preservation requirements are user-provided facts. No Railway/external resources were changed. No application code was changed during this audit. Only two test files were corrected, in commit `48367d7c4c4a4d89d8a1179041f3509d20e1ec5e`, separately from Telegram fix `2368104bc481c2f1fce9fb3b813827708adb0ea3`.

There are no tracked Railway manifests, Dockerfiles, Procfiles or deployment workflows. Service names below are **functional labels to map onto existing Railway services**, not verified dashboard names. Confirm the dashboard names after upgrading to Hobby. The owner reports existing commands `uvicorn main:app` and `python -m backend.commands.process_access_fulfillments`; their actual dashboard roots/build settings remain unverified. The recommended commands below make root, bind address and port explicit. Preserve the existing environment, PostgreSQL service, volume, credentials and data; that environment becomes production. Production eventually deploys from `main`, after a separately authorized review/merge. Nothing in this task authorizes that merge or deployment.

The complete, secret-free configuration table is in [production-environment-variables.md](production-environment-variables.md).

## 1. Blocking launch issues and concrete risks

| Priority | Finding and repository evidence | Required resolution before launch |
|---|---|---|
| Blocker | Existing database may contain sandbox Stripe objects and channel mappings. `ensure_public_monthly_plan_configured` returns existing plans without replacing their price; checkout requires exact configured price. Channel bootstrap rejects conflicts. Workers use stored channel mappings. | Inspect existing rows with owner; agree an explicit, backed-up test-to-live mapping transition. Merely switching environment secrets is insufficient. Do not delete/reset history. |
| Blocker | Staging duplication copies configuration; changing only `DATABASE_URL` does not isolate Stripe, email or Telegram. There is no global email sandbox override. | Separate DB, bot/channel, Stripe sandbox, sender credentials and test recipients before any copied application/worker starts. Do not allow restored production queues to send to real subscribers. |
| Blocker | `state.py` writes root `state.json`; `scheduler.py` writes `data/prices_clean.csv`. They are ignored by Git and not in PostgreSQL. Missing state silently initializes default positions. | Preserve existing strategy state/history and choose durable storage/startup layout. Mounting only `data/` does not preserve `state.json`. No configurable state path exists. Resolve before scheduler start. |
| Blocker | Scheduler appends today's CSV row before strategy completion/DB signal persistence. A subsequent failure can leave a row that makes `start_scheduler` skip the unfinished day. State-file saves are direct, not atomic with database writes. | Design durable completion/recovery or an explicit monitored recovery procedure; do not assume CSV presence proves daily processing succeeded. No fix made. |
| Blocker for accurate public market display | `backend/routers/market.py` serves latest stored prices without checking age or returning freshness; uses fixed `USD_EUR_RATE = 0.92`; reads a local top-level signal state while strategy state is per-module and lives in another service. | Approve/correct market freshness, FX and signal-display semantics. The two stale tests are not the cause of these separate application issues. |
| Blocker | Public legal routes all render `LegalPlaceholder`; company legal fields are null and the trademark marker is hardcoded. | Owner supplies approved product/legal/company content. This is an observed content gap, not legal advice. |
| Configuration gate | JWT has a known insecure fallback; public admin operations remain mounted. | Supply a strong secret and approved admin provisioning/operations procedure. `/auth/login` and admin UI/login routes are not active. Do not enable legacy customer routes just to obtain an admin token. |
| Configuration gate | Root requirements omit backend dependencies; backend requirements omit strategy dependencies. No locked Python dependency set/runtime version. | Use both requirements files for Python services below; validate a clean Railway/staging build and record versions. Current local Python tests used 3.11. |
| Configuration gate | `frontend/package.json` exposes only dev/build/preview, and preview allows all hosts. | Use Railway Railpack's Vite static/Caddy mode with no custom preview start command; verify generated deployment plan and SPA deep links. No source change is needed if Railpack detection works. |
| Operational gate | `/health` is unconditional, background failures may be returned as counters with CLI exit 0, no continuous provider/queue monitoring configured in repo. | Monitor DB, queue ages, failed counters, scheduler completion and provider results independently. Do not use process success as delivery success. |
| Operational risk | Membership-removal claim selection is not a locked compare-and-set operation; signal/fulfillment claims have stronger protections. | Run exactly one removal worker; no simultaneous manual duplicate runs. PostgreSQL concurrency testing still needed before scaling. |
| Known residual | Provider acceptance followed by process loss before DB commit remains ambiguous for email delivery. | Incident reconciliation with Brevo; do not promise crash-proof exactly-once delivery. Persistent acknowledgement prevents normal renewal resends. |

The market adapter itself is explicitly labeled a development Yahoo Finance adapter (`market_data.py`) and uses futures tickers for metals. Confirm intended data quality, market timing and production data-source suitability; tests with mock data do not certify those external assumptions.

## 2. Exact service layout and commands

These are proposed dashboard settings supported by the repository, not changes already applied. Keep existing service identities. Use a single replica initially for each process. Set Python services' root to repository `/` so `market_data.py`, `state.py`, `config.yaml`, scheduler and backend modules remain present.

**Python build command for API and all Python workers:**

```sh
pip install -r backend/requirements.txt -r requirements.txt
```

| Service role | Railway root | Start command / build | Schedule / health |
|---|---|---|---|
| `PostgreSQL` (existing) | Existing service/image/volume | Preserve existing start, image version and mount | Always available; backups enabled |
| `backend-api` | `/` | `uvicorn main:app --app-dir backend --host 0.0.0.0 --port "$PORT" --workers 1` | Persistent web service; `/health` |
| `frontend` | `/frontend` | Build `npm ci --include=dev && npm run build`; **leave custom Start Command empty** for Railpack Vite SPA/Caddy detection; `dist` output | Persistent static service; `/` health; no DB access |
| `access-fulfillment-worker` | `/` | `python -m backend.commands.process_access_fulfillments --limit 2` | Railway cron `*/5 * * * *`; no HTTP health check |
| `signal-publication-worker` | `/` | `python -m backend.commands.process_signal_publications --limit 2` | Railway cron `*/5 * * * *`; no HTTP health check |
| `membership-removal-worker` | `/` | `python -m backend.commands.process_access_removals --limit 5` | Railway cron `*/5 * * * *`; single runner, no `--now` override |
| `strategy-scheduler` | `/` | `python scheduler.py` | One persistent worker, **no Railway cron**; internal weekdays 17:05 Europe/Paris, with post-time startup catch-up; storage gate above must be resolved |

Railpack detects this repository's `vite.config.ts` and build script, uses Caddy for static output and supports `RAILPACK_SPA_OUTPUT_DIR=dist`. A custom start command disables that mode. Inspect the build plan rather than assuming an existing service already uses it. [Railpack Node/static-site documentation](https://railpack.com/languages/node). Do not use `npm run dev` or `npm run preview` as a production server; [Vite explicitly excludes preview for production](https://vite.dev/guide/static-deploy).

Railway cron minimum is five minutes and schedules are UTC. Earlier repository guidance suggesting once per minute cannot be implemented with Railway cron. The internal strategy scheduler avoids DST conversion; if choosing `python scheduler.py --now` with external scheduling instead, weekdays 17:05 Paris are 15:05 UTC in summer and 16:05 UTC in winter, and `--now` needs its CSV history already initialized. Do not run both scheduler models. [Railway cron documentation](https://docs.railway.com/cron-jobs).

At limit 2 per five-minute pass, each delivery worker drains at most 24 rows/hour through cron, plus immediate API/scheduler passes. Increase capacity only after measuring backlog and reviewing worker limits; passing a limit above 2 is rejected. A backlog of onboarding emails may exceed the expected customer wait despite an otherwise healthy API.

Do not expose worker public domains. The root API build deliberately includes all dependencies; a clean installation has not been performed in Railway. Pin/review runtime versions rather than relying on changing platform defaults. Frontend tests require a Node runtime supporting TypeScript test files; use an explicitly reviewed compatible Node version (Vite 8 requires a sufficiently recent runtime).

## 3. Health, routing and security

- `GET /health` returns 200 with `{"status":"ok"}` after startup. It checks neither PostgreSQL connectivity/schema nor plan, bot or email readiness. It is suitable for Railway process-start routing, **not sufficient launch readiness**. Configuration bootstrap errors are logged and swallowed, so health can be green while checkout/fulfillment is unavailable.
- Railway checks health at deployment, not continuously; add external uptime and operational checks separately. If host restriction is added later, include `healthcheck.railway.app`. [Railway health checks](https://docs.railway.com/deployments/healthchecks).
- CORS allows localhost ports 5173/3000 plus the single origin from `PUBLIC_APP_URL`; credentials enabled, all methods/headers allowed. Invalid public-origin configuration is silently omitted from CORS. There is no `CORS_ORIGINS` reader or `TrustedHostMiddleware`/`ALLOWED_HOSTS` setting. Choose a canonical frontend host; a second www/apex host needs a redirect or later code change.
- No cookie/session middleware or `set_cookie` path was found. Public checkout is accountless. Billing management uses opaque, expiring, single-use email tokens, hashed in PostgreSQL; link tokens are in a URL fragment and consumed/removed by the frontend. Public HTTP clients do not carry the legacy JWT automatically.
- Admin operations require an active legacy User with `aurum` membership and bearer JWT. JWT uses HS256, `sub` and expiry; no issuer/audience/refresh-token workflow. Legacy frontend stores JWT in localStorage, but admin/customer pages are not mounted by current `App.tsx`. Backend `/auth/login` in OAuth documentation points to an unmounted router.
- Rate limits use SlowAPI in-process storage and `get_remote_address`: checkout and portal exchange 10/minute, portal link and contact 5/minute. Verify trusted proxy/client-IP behavior on Railway. Multiple API processes have separate limit counters; no Redis limiter configured.
- FastAPI debug is not enabled, but `/docs`, `/redoc`, `/openapi.json` are public and Swagger persists authorization. Decide whether public API documentation is acceptable. No environment flag currently disables it.
- Secret-pattern scan of tracked files found only test fixtures; no actual hardcoded provider secret was identified. This is not a historical Git secret audit or verification of untracked local/provider secrets. Known insecure JWT fallback remains. Do not commit `.env` files; `.gitignore` does not cover every possible `.env.production` spelling.
- Dormant auth uses in-memory verification/reset tokens, fixed dev codes outside `ENV=production`, and prints verification codes if sending fails. Dormant IBKR disables TLS verification by default. These must stay outside launch; neither is made safe by the current test corrections.
- `create_test_signal` CLI refuses execution if ENV or APP_ENV is production; there is no mounted public test-signal route. Strategy override variables are separately gated and can still be enabled in production if misconfigured. Removal CLI `--now` permits time override without a production guard; never use it for production scheduling.

## 4. URLs and provider configuration

Exact deployed domains are **not known from repository configuration**. Let **F** be the chosen production frontend HTTPS origin and **B** the backend HTTPS origin; use independent **SF/SB** for staging. Hardcoded contact branding at auroratio.com and `docs/CNAME` are not proof of API hosting/DNS.

Owner-approved documentation placeholders (do not enter these literal strings into service configuration):

| Symbol | Placeholder |
|---|---|
| F | `https://<production-frontend-domain>` |
| B | `https://api.<production-domain>` |
| SF | `https://<staging-frontend-domain>` |
| SB | `https://<staging-api-domain>` |

### Every location that needs final domain configuration/review

1. Railway public-domain settings for `frontend` and `backend-api` in each environment, plus DNS records and TLS verification with the domain owner. Worker services need no public domains.
2. Backend `PUBLIC_APP_URL` in each environment: supplies the one allowed non-local CORS origin and constructs checkout success/cancel, billing-link and portal-return URLs. No separate callback-variable values need entering for those derived URLs.
3. Frontend build `VITE_API_URL` in each environment: consumed by `src/api/publicBilling.ts`, `publicMarket.ts`, and retained `client.ts`; rebuild after changes. Never use a private Railway backend hostname in browser configuration.
4. Stripe owner's webhook endpoint in each account/mode: `B/stripe/webhook` and `SB/stripe/webhook`; issue separate matching signing secrets. Review any dashboard-configured portal/business website/allowed return domains against the chosen frontend. The application already passes its derived return URL.
5. Telegram webhook registration for each separate bot: `B/telegram/webhook` or `SB/telegram/webhook`, with the correct webhook secret. Changing API environment variables does not update provider webhook registrations.
6. Any external scheduler, monitoring or admin client calling backend URLs must use the matching environment's backend origin. In-process worker commands use PostgreSQL/provider configuration, not these public URLs.
7. Choose canonical www/apex routing; redirect the alternate frontend host to the canonical one because backend CORS admits only the one configured origin. If host middleware/static-server host restrictions are later added, include the final frontend/backend hosts as appropriate and Railway's healthcheck hostname.
8. `docs/CNAME` currently contains `auroratio.com`: review its existing GitHub Pages/DNS role before reusing that domain for Railway; do not silently change/delete it or assume it configures Railway.
9. `frontend/src/config/companyInformation.ts` contains `contact@auroratio.com` and `support@auroratio.com`. Review these mailbox domains alongside Brevo `BREVO_SENDER_EMAIL`, `CONTACT_TO_EMAIL`, sender verification and email DNS records; mailbox domains do not have to match API/staging hosts. No canonical/sitemap/robots domain setting was found in `frontend/index.html` or `frontend/public` during this audit.
10. `FRONTEND_URL` only belongs to unmounted legacy auth/broker flows. If those are ever separately activated, configure it then and audit reset/callback routes. It is not the active public billing URL and should not be used instead of `PUBLIC_APP_URL`.


| Purpose | Exact URL construction |
|---|---|
| Frontend | `F` → `PUBLIC_APP_URL`; staging `SF` |
| Browser API | `B` → frontend build `VITE_API_URL`; staging `SB` |
| API health | `B/health` |
| Stripe webhook | `B/stripe/webhook` |
| Telegram webhook | `B/telegram/webhook`, header `X-Telegram-Bot-Api-Secret-Token` |
| Checkout success | `F/subscription/success?session_id={CHECKOUT_SESSION_ID}`; frontend removes the query parameter |
| Checkout cancellation | `F/subscription/cancelled` |
| Billing request page | `F/manage-subscription` |
| Emailed billing access | `F/manage-subscription/access#token=<opaque-token>` |
| Stripe billing portal return | `F/manage-subscription?portal=return` |
| Contact API | `B/contact` |
| Email verification / password reset | **Not part of the active product.** Legacy code exposes verification endpoints only in an unmounted auth router, and builds `FRONTEND_URL/reset-password?token=...`; current frontend redirects that path home. Do not give these URLs to customers. |
| Broker callback | Retained broker router is unmounted; no production callback to configure for this launch |

Stripe redirects are server-selected, not user-provided. Payment submission pages intentionally do not confirm paid access. Only verified events update entitlement state. There is no frontend Stripe publishable key requirement: checkout is hosted and opened from backend response.

Brevo uses HTTPS transactional endpoint with a 15-second HTTP timeout. Required production sender/domain authentication and account sending permission must be checked by owner. Onboarding goes to `stripe_email` or `normalized_email`; billing links go to requesting eligible email; contact goes to `CONTACT_TO_EMAIL`. There is **no application-level recipient override**, no ENV-based Brevo sandbox, and no email dry-run switch. `EMAIL_TO` controls only dormant Gmail alerts. Staging must use controlled email addresses and a separately isolated provider configuration; a different API key is not by itself a recipient allowlist. Missing Brevo key returns failure, not success. Provider HTTP acceptance is not inbox-delivery proof.

Telegram bot must be able to create invites, receive relevant `chat_member` updates and restrict/remove members. Use separate staging bot/channel: registering a staging webhook on a shared bot can interfere with production delivery. Membership removal depends on binding a member to the actual invitation; missing membership updates mean expired members may remain in the channel. Verify join tracking and removal end-to-end.

## 5. PostgreSQL, migration and preservation

The current application migration head is `a7d3e9f102bc`, parent `6f8a2c4d9e10`. With the documented repository-root API service, set **only the API's Railway Pre-Deploy Command** to:

```sh
cd backend && alembic upgrade head
```

If retaining a service rooted at `/backend`, the equivalent is `alembic upgrade head`, but verify that service still packages needed root modules. Use production `DATABASE_URL` referencing the preserved PostgreSQL service; never a hardcoded staging URL. `alembic/env.py` reads that variable and ignores the dummy URL in alembic.ini. Do not use `alembic stamp`, recreate tables or point at a new empty database to avoid migration errors.

Pre-deploy runs in a separate container with service variables/private network; application volumes are not mounted. This is appropriate for PostgreSQL and not for backing up scheduler files. Set a measured pre-deploy timeout; do not start workers on migration failure. [Railway pre-deploy](https://docs.railway.com/deployments/pre-deploy-command).

`a7d3e9f102bc` updates every fulfillment with non-null `delivered_at`: sets delivered status and clears retry/claim/error fields. It does not create a timestamp or infer delivery from billing state. Rows with null acknowledgement remain untouched. It trusts historical timestamps, including any erroneous provider acknowledgements recorded by older code. Review anomalous non-delivered rows with timestamps against Brevo/audits. Existing correct delivered rows are also rewritten. Upgrade and version update are transactional on PostgreSQL; locks persist to commit, competing row writes may wait. Downgrade to the parent does not undo the data repair. Clearing old error fields is irreversible without backup; audit records are retained. Earlier downgrades can remove tables and are not a safe production rollback strategy.

Before migrating:

1. Record service/volume IDs, PostgreSQL version, existing revision, table counts and current DB references without exposing credentials.
2. Take a Railway PostgreSQL-volume backup and an encrypted logical `pg_dump` using a client compatible with the server. Keep dumps outside Git and restrict access.
3. Verify a restore into an isolated non-production database, then compare schema/counts and critical subscription, entitlement, fulfillment, membership, audit and integration-event records. A backup that has never been restored is not sufficient evidence.
4. Preserve `state.json` and price history independently of PostgreSQL.
5. Review all pending migrations if current revision is not the parent. No production revision/counts were inspected here.

Enable suitable recurring backups and alerts; current Railway documentation lists daily retention 6 days, weekly 27 days and monthly 89 days. Confirm availability/cost on the actual Hobby plan and choose recovery objectives; do not assume PITR is enabled. [Railway backups](https://docs.railway.com/volumes/backups).

### Exact processes to pause for a7d3e9f102bc

**Must stop/drain:** every old backend API replica (Stripe background tasks and admin fulfillment endpoints can send), every `process_access_fulfillments` invocation/cron/loop, and any external caller invoking fulfillment process/retry/backfill or subscription replay/synchronization. Stop new triggers first; let active provider requests finish. Avoid forced termination between acceptance and commit. No built-in maintenance/drain toggle exists.

**Can remain running for this specific data repair:** PostgreSQL, static frontend, strategy scheduler, signal-publication worker and membership-removal worker: none writes the repaired fulfillment delivery fields. For the wider test-to-live credential/mapping cutover, pause **all provider-facing workers**, including scheduler, publications and removals, to avoid sending/removing against mixed environments.

A rolling API deployment or pausing only cron does not provide this pause. Graceful shutdown settings need sufficient time and verification of completion. If any send was force-killed, reconcile that attempt before re-enabling retries.

## 6. Persistent storage and daily processing

- PostgreSQL stores subscribers, entitlements, delivery claims/results, integration events, billing tokens, memberships, signal/publication records and market snapshots. Preserve its existing volume.
- Scheduler needs root `state.json` and `data/prices_clean.csv` across restarts. `state.py` has no storage-path environment setting. There is no safe, verified volume/startup wrapper in this repository. Choose a reviewed path-configuration or staging-tested startup copy/symlink layout; do not mount an empty volume over application source. No such change was made here.
- API cannot assume it sees scheduler-local files. Even copying the current per-module state file does not implement the top-level `signal/current_metal` format expected by the market endpoint. Shared market prices already use PostgreSQL; signal display needs its own decision.
- `data/prices_raw.csv`, clean historical data, cycle logs and optional Yahoo cache are local. Preserve the inputs/state needed for strategy continuity; rotate/ship logs separately. Generated backtest artifact `backend/static/backtest_results.json` is tracked/read-only and must be packaged, not regenerated at startup.
- Scheduler refreshes a market snapshot at startup and processes weekdays at 17:05 Paris. Each day is attempted once per process; a successful file write followed by downstream failure is not recovered reliably by restart. There is no nightly Stripe subscription-sync job in the repository.
- An empty history can trigger download on persistent scheduler startup; `--now` does not initialize history automatically. Do not rely on fresh downloads as restoration of lost strategy positions.

## 7. Background and fulfillment paths

1. `/stripe/webhook`: signature verification → persisted/deduplicated integration event → retrieve Stripe subscription → update entitlement → enqueue unique entitlement/mapping fulfillment.
2. Checkout completed, subscription created/updated, `invoice.paid`, `invoice.payment_succeeded` schedule an immediate one-row background fulfillment pass. Renewal is not a distinct direct email sender.
3. `process_access_fulfillments` CLI provides durable periodic retries.
4. `/admin/fulfillment/process-due`, `/{id}/retry`, `/backfill` use the same fulfillment service. Backfill queues missing work; manual retry does not itself send.
5. Internal `replay_stripe_integration_event` uses the same ingestion/enqueue path; no separate nightly replay CLI exists.
6. API startup bootstraps plan/channel mappings only; it does not backfill or send invitations.
7. Strategy scheduler ingests confirmed decisions and immediately drains bounded signal publications; `process_signal_publications` and admin publication routes also publish. These are channel messages, not onboarding emails.
8. `/telegram/webhook` records membership binding. `process_access_removals` reconciles expired access; it does not send onboarding mail.
9. `/public/billing/portal-link` uses a separate API background email batch. It is not the Telegram invitation queue; monitor failure/re-request behavior independently.

## 8. Safe Railway sequence for the owner

1. Upgrade the existing project to Hobby **without deleting/recreating the existing environment, DB service or volume**. Before provider-facing processes resume, inspect existing deployments/schedules. The trial expiry does not establish which processes will resume automatically.
2. Capture existing service roots, commands, branches, domains, variable *names*, DB references, PostgreSQL version and backup status. Map actual names to the service table. Keep production attached to `main` with automatic deployments controlled during the rollout.
3. Preserve backups and provider mappings as above. Keep all outbound workers paused during environment isolation.
4. Duplicate the environment into staging after upgrade. Review staged changes **before deploying**: staging PostgreSQL must have its own service/volume and all connection references must resolve there. Do not assume copying the environment creates a sanitized dataset or transfers/restores volume data. Start DB first. Inspect it before any application starts.
5. Replace copied Stripe/Brevo/Telegram credentials and public origins with isolated staging values. Prefer synthetic customers/queues. If using a production restore for migration rehearsal, keep outbound services disabled and neutralize external identities through a separately reviewed sanitization plan before testing sends. [Railway environment duplication](https://docs.railway.com/environments).
6. Point staging at this feature branch. Configure roots/build commands, API-only pre-deploy migration, health check, static serving and schedules; leave workers paused. Resolve durable scheduler storage first.
7. Migrate staging, start API, then build/start frontend using staging API URL. Validate origin/host/deep-link behavior. Register staging provider webhooks only on staging resources. Enable staging fulfillment, publication, removal and finally strategy scheduler; smoke-test the full lifecycle.
8. Restore a production backup to an isolated test DB and rehearse pending migrations and data preservation. Validate real PostgreSQL transaction/locking behavior; SQLite passing tests do not cover all PostgreSQL behavior.
9. Review and fix the remaining launch blockers in separate authorized work. Obtain Stripe-owner signoff and decide domains, operational access, market data, storage and legal content.
10. After separate authorization, merge approved code into `main`. **Not done by this task.** Preserve the existing production environment and database; do not deploy this feature branch directly as production.
11. During a planned production window: stop new fulfillment triggers, gracefully stop all API replicas and fulfillment workers; for live credential/mapping transition stop scheduler/publication/removal workers too. Back up and review acknowledgement/mapping anomalies.
12. Run the API pre-deploy migration once against existing production PostgreSQL; verify head and preserved counts. Start updated API only after success. Confirm live mappings before opening checkout. Deploy frontend built with production API URL, then enable fulfillment, publications, removals and scheduler in that order after checks. Keep all services on reviewed `main` revision.
13. Restore schedules/autodeploy policy only after smoke tests. If migration fails, keep senders stopped, diagnose, and retain database backup. Do not stamp past a failure or restore a backup over newly accepted payments without reconciliation.

## 9. Smoke tests (staging first; production only with explicit owner approval)

- `/health` returns 200; database accessible; Alembic head correct; configuration rows match intended Stripe mode, plan and Telegram channel. Verify logs contain no bootstrap-skipped warning.
- Frontend `/`, `/subscription/success`, `/subscription/cancelled`, `/manage-subscription/access` deep links load after refresh; JS assets load; no localhost/test backend in production bundle.
- Browser CORS works for canonical origin; an unrelated Origin gets no allow-origin response; verify real client-IP rate limits. Unauthenticated admin endpoints reject access. `/auth/login`, signup, reset-password and test routes are not unexpectedly active.
- Unsigned Stripe and missing-secret Telegram requests fail without DB changes. Provider-signed test events reach their intended environment only.
- In staging, first paid activation produces one invitation and acknowledgement, then join binds membership. Replay event and run both invoice success types/renewals/backfills/worker passes: no second onboarding email; access dates extend.
- Simulate initial email failure using isolated provider setup: no acknowledgement, bounded retry, successful later acknowledgement. No real recipient receives staging mail.
- Cancel-at-period-end preserves access until the deadline; expiry removes a correctly bound member; delinquency/grace behavior matches existing rules. Use Stripe sandbox/test clocks, not production `--now` overrides.
- Billing management sends only eligible generic links; token is one-use and expiring, replay fails, Stripe portal returns to correct frontend. Unknown email gets indistinguishable response. Contact email reaches intended inbox.
- Strategy fixture/dry-run validation uses no production test overrides. In staging, check one real scheduled run writes fresh market data and intended signal, survives restart with the same state/history, and does not duplicate publication. Exercise failed-run recovery rather than relying only on happy-path daily execution.
- Inspect queue counts/oldest pending times and provider delivery logs. Watch CLI failure counters even when exit code is 0. Verify backup restore and alerting before declaring readiness.
- Any live purchase/cancellation smoke test, live invite, or production publication requires explicit owner coordination; none was performed here.

## 10. Stripe-owner handoff

- Supply live `STRIPE_SECRET_KEY`, production endpoint `STRIPE_WEBHOOK_SECRET`, live `STRIPE_MONTHLY_SIGNAL_PRICE_ID`, and reviewed portal configuration ID securely; keep keys out of Git/chat/frontend.
- Create/confirm separate staging sandbox keys, price and webhook secret. Configure production webhook `B/stripe/webhook`, staging `SB/stripe/webhook`.
- Enable the seven supported events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_succeeded`, `invoice.payment_failed`.
- Confirm the supported Stripe API payload version by staging tests, including invoice subscription references and current period fields. No live-mode guard in ingestion automatically rejects a correctly signed sandbox event: correct endpoint/account/mode configuration matters.
- Confirm €14.99/month public offer matches live amount, currency, billing interval, taxes, supported payment methods and portal cancellation settings. These Stripe dashboard settings are not controlled by this repository.
- Coordinate the existing DB's test-price/customer/subscription history transition; do not overwrite identities or assume live credentials can retrieve sandbox objects. Keep `monthly-signals` consistent with the frontend.
- Confirm asynchronous payment behavior for chosen methods, dunning policy versus the application's fixed three-day grace period, and controlled live smoke-test approval.

## 11. Test-failure findings and verification

1. `test_scheduler_startup_refresh_fetches_validates_and_persists_idempotently`: fixed August 13 fixture reached real wall-clock freshness validation. As time passed, valid-for-test observations became stale. Fix freezes only the market validator's clock at fixture time; real validation and all persistence assertions remain.
2. `test_scheduler_market_write_failure_does_not_interrupt_signal_workflow`: same clock mismatch prevented reaching the deliberately failed persistence call and checking continued strategy work. Same test-only clock control restores intended coverage; no freshness limit was increased.
3. Frontend `success and cancellation routes are honest and accountless`: assertions expected wording/steps deliberately replaced in commit `0a9d9c2` with conditional payment-submitted copy. Updated assertions check conditional email delivery, waiting guidance, French conditional wording and cancellation uncertainty. Accountless/manual-trading/session-ID safety checks remain.

Results after corrections:

- `.venv/bin/python -m pytest backend/tests -q`: **349 passed**, six dependency/framework deprecation warnings.
- `npm test` in frontend: **39 passed**, Node TypeScript-stripping experimental warnings.
- `npm run build` in frontend: **passed**; large JavaScript chunk warning remains (~869 kB uncompressed).
- `git diff --check`: passed before test commit.
- No Railway build, live provider integration, PostgreSQL restore or production smoke test was performed. Generated build state was not committed.

## 12. Decisions still required

Dashboard service names/root settings and final domains (the owner has explicitly deferred the domain choice; placeholders above are sufficient for this audit); safe scheduler-state storage and failure recovery; live DB mapping transition; staging dataset/provider isolation; approved legal/product content; trustworthy market freshness/FX/signal display; authenticated operator access; worker capacity and latency; backup recovery objectives; proxy/rate-limit/documentation exposure policy. The repository alone cannot supply these facts or authorize their external implementation.
