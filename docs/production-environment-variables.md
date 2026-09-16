# Production environment-variable inventory

Repository audit on `fix/telegram-email-idempotency`, September 15, 2026. No secret values or Railway variable values were read. “Keep” means keep the documented policy/default if already configured correctly, not confirmation of the current deployment's value. Production retains the existing database/environment; staging must reference a separate database. Do not copy literal production database URLs or credentials into staging.

This inventories direct application reads, dynamically named reads, Vite configuration, and retained inactive code. Runtime-library/platform settings are listed separately; arbitrary variables consumed internally by third-party dependencies are not application configuration.

## Active accountless product

Final domains are intentionally undecided. Use only the documentation placeholders listed in the companion audit; never enter their literal angle-bracket strings into Railway. Actual dashboard service names must be confirmed after the Hobby upgrade.

Scopes: **API** = backend API; **F** = access-fulfillment worker; **P** = signal-publication worker; **R** = membership-removal worker; **S** = strategy scheduler; **M** = migration runner. All Python processes load `backend/.env` if present; deploy with Railway variables, not a packaged `.env`. Environment changes require process restart. Frontend variables require rebuilding.

| Variable | Scope / code default | Production action | Staging action / owner |
|---|---|---|---|
| `DATABASE_URL` | API/F/P/R/S/M; required | Preserve reference to existing PostgreSQL; use `postgresql://` or `postgresql+psycopg2://`, not SQLite or `postgres://` | Reference staging PostgreSQL only; operator |
| `PUBLIC_APP_URL` | API; required for billing; no default | Exact HTTPS public frontend origin, no path/query; also controls CORS | Staging frontend origin; operator |
| `VITE_API_URL` | Frontend build; no default | Exact HTTPS public backend origin; browser cannot use Railway private DNS | Staging backend origin at build time; operator |
| `JWT_SECRET_KEY` | API; unsafe built-in fallback | Strong private signing secret; preserve only if already strong/private; plan rotation if not | Independent signing secret; operator |
| `JWT_TOKEN_EXPIRE_HOURS` | API; `24` | Keep or explicitly decide a shorter admin-token lifetime | Same policy; operator |
| `ENV` | Test-signal CLI / retained auth; default development in retained auth | Explicit `production` | Prefer `production` for parity; use staging value only for isolated intentional CLI tests; operator |
| `APP_ENV` | Test-signal CLI; unset | Explicit `production` as additional guard | Same parity rule; either variable being production blocks test-signal creation; operator |
| `LEGACY_CUSTOMER_APP_ENABLED` | Backend retained guards and frontend build via explicit Vite define; false | Keep `false`; launch routers remain unmounted regardless | `false`; operator |
| `STRIPE_SECRET_KEY` | API; required | Live account secret delivered securely | Test/sandbox secret; **Stripe owner** |
| `STRIPE_WEBHOOK_SECRET` | API; required | Signing secret for production `/stripe/webhook` endpoint | Separate staging endpoint secret; **Stripe owner** |
| `STRIPE_MONTHLY_SIGNAL_PRICE_ID` | API; required | Live monthly price matching public offer and existing plan row; changing env does not migrate DB mapping | Test monthly price and staging DB mapping; **Stripe owner + operator** |
| `STRIPE_BILLING_PORTAL_CONFIGURATION_ID` | API; optional, otherwise Stripe account default | Reviewed live portal configuration | Test portal configuration; **Stripe owner** |
| `MONTHLY_SIGNAL_PLAN_CODE` | API/S; public billing defaults `monthly-signals`, Telegram bootstrap requires explicit value | Set `monthly-signals`; frontend sends this exact code | Same code in separate DB; operator with Stripe owner for mapping |
| `PORTAL_ACCESS_TOKEN_TTL_MINUTES` | API; `15`, max 60 | Keep `15` | Same; operator |
| `PORTAL_LINK_COOLDOWN_MINUTES` | API; `5`, max 1440 | Keep `5` | Same; operator |
| `PORTAL_REQUEST_MIN_RESPONSE_MS` | API; `750`, range 0–5000 | Keep `750` anti-enumeration response floor | Same; operator |
| `BREVO_API_KEY` | API/F; required to send | Production-scoped provider credential | Separate scoped credential/provider isolation; key alone does not redirect recipients; operator |
| `BREVO_SENDER_EMAIL` | API/F; `no-reply@auroratio.com` | Verify authenticated sender/domain; keep if approved | Verified staging sender; operator |
| `BREVO_SENDER_NAME` | API/F; `AuroRatio` | Keep | Distinguishable staging sender name; operator |
| `CONTACT_TO_EMAIL` | API; `support@auroratio.com` | Confirm intended inbox; website advertises contact and support separately | Controlled test inbox; changes contact form only, not subscriber emails; operator |
| `TELEGRAM_BOT_TOKEN` | API/F/P/R/S; required for external operations | Production bot, required channel admin rights | Separate staging bot; operator |
| `TELEGRAM_WEBHOOK_SECRET_TOKEN` | API; required | Strong secret matching Telegram webhook registration | Independent secret; operator |
| `TELEGRAM_CHANNEL_ID` | API bootstrap; required nonzero integer | Existing intended production channel and consistent database row | Distinct test channel and staging database row; operator |
| `TELEGRAM_CHANNEL_CODE` | API bootstrap; `private-signals` | Keep stable database identity | Same logical code is safe in separate DB; operator |
| `TELEGRAM_CHANNEL_DISPLAY_NAME_EN` | API bootstrap; `AuroRatio Private Signals` | Keep intended label; existing row is not renamed by env | Optional staging label on newly created configuration; operator |
| `TELEGRAM_CHANNEL_DISPLAY_NAME_FR` | API bootstrap; `Signaux privés AuroRatio` | Keep intended label | Optional staging label; operator |
| `TELEGRAM_API_BASE_URL` | Telegram clients; `https://api.telegram.org` | Keep official HTTPS endpoint; custom host receives bot credential | Official endpoint with separate bot, or explicitly controlled mock; operator |
| `TELEGRAM_INVITE_TTL_HOURS` | F; `24`, max 168 | Keep `24`; email copy promises 24 hours | Same to test actual behavior; operator |
| `TELEGRAM_PROVIDER_TIMEOUT_SECONDS` | Telegram clients; `10`, max 60 | Keep `10` | Same; operator |
| `ACCESS_FULFILLMENT_MAX_ATTEMPTS` | F/API background; `5` | Keep | Same; operator |
| `ACCESS_FULFILLMENT_RETRY_SECONDS` | F/API background; `300` | Keep | Same; operator |
| `ACCESS_FULFILLMENT_CLAIM_LEASE_SECONDS` | F/API background; `900` | Keep; must exceed normal processing duration | Same; operator |
| `SIGNAL_PUBLICATION_MAX_ATTEMPTS` | P/API/S; `5` | Keep | Same; operator |
| `SIGNAL_PUBLICATION_RETRY_SECONDS` | P/API/S; `300` | Keep | Same; operator |
| `SIGNAL_PUBLICATION_CLAIM_LEASE_SECONDS` | P/API/S; `900` | Keep | Same; operator |
| `ACCESS_REMOVAL_MAX_ATTEMPTS` | R; `5` | Keep | Same; operator |
| `ACCESS_REMOVAL_RETRY_SECONDS` | R; `300` | Keep | Same; operator |
| `ACCESS_REMOVAL_CLAIM_LEASE_SECONDS` | R; `900` | Keep | Same; operator |
| `SUBSCRIBER_SIGNAL_PLAN_CODES` | S; falls back to monthly plan code then `monthly-signals` | Explicit `monthly-signals` for launch; DB mappings must agree | Same logical code with isolated channel; operator |
| `AURORATIO_STRATEGY_TIMEZONE` | S; `Europe/Paris` | Keep; internal scheduler runs weekdays 17:05 in this timezone | Same; operator |
| `MARKET_DATA_MAX_AGE_DAYS` | S; `4` | Keep freshness limit; do not increase to hide stale data | Same; operator |
| `MARKET_DATA_LOCAL_FILE_FALLBACK` | API; `true` but SQLite-only | Explicit `false`; PostgreSQL already disables fallback | `false` for PostgreSQL parity; operator |
| `AURORATIO_ENABLE_STRATEGY_TEST_OVERRIDES` | S/state; false | Explicit `false`; production mode does not independently block this flag | Normally false; isolated tests only; operator |
| `AURORATIO_TEST_TRADE_DELAY_DAYS` | S/state; unset, positive integer | Unset | Unset except intentional isolated strategy tests; operator |
| `AURORATIO_TEST_SILVER_BUY_RATIO` | S/state; unset | Unset | Isolated tests only; operator |
| `AURORATIO_TEST_SILVER_SELL_RATIO` | S/state; unset | Unset | Isolated tests only; operator |
| `AURORATIO_TEST_PLATINUM_BUY_RATIO` | S/state; unset | Unset | Isolated tests only; operator |
| `AURORATIO_TEST_PLATINUM_SELL_RATIO` | S/state; unset | Unset | Isolated tests only; operator |
| `AURORATIO_TEST_PALLADIUM_BUY_RATIO` | S/state; unset | Unset | Isolated tests only; operator |
| `AURORATIO_TEST_PALLADIUM_SELL_RATIO` | S/state; unset | Unset | Isolated tests only; operator |

Sources: `backend/database.py`, `backend/core/public_urls.py`, `backend/dependencies.py`, `backend/main.py`, `backend/services/{public_billing_service,private_channel_bootstrap_service,email_service,subscriber_fulfillment_service,subscriber_signal_publication_service,telegram_private_channel_service,telegram_membership_service,telegram_updates,strategy_signal_bridge_service}.py`, `backend/commands/create_test_signal.py`, `frontend/vite.config.ts`, `frontend/src/api/*.ts`, `state.py`, `market_data.py`, `scheduler.py`.

## Retained legacy functionality: leave disabled/unset in both environments

These reads exist in the repository, but their customer routers/trading scheduler are not mounted/started by `backend/main.py`. They are not required for the accountless launch. Do not supply live broker permissions. Defaults here document the source, not a recommendation to activate these features.

| Variable | Source / current default | Production / staging treatment |
|---|---|---|
| `FRONTEND_URL` | Auth/broker routers; localhost origin | Unused for active billing; if ever enabled, separate HTTPS frontend origin per environment |
| `EMAIL_CODE_TTL_MINUTES` | Auth; `15` | Dormant; keep default |
| `PHONE_CODE_TTL_MINUTES` | Auth; `15` | Dormant; keep default |
| `RESET_TOKEN_TTL_MINUTES` | Auth; `30` | Dormant; keep default |
| `DEV_EMAIL_CODE` | Auth; fixed development code | Unset; do not activate legacy auth |
| `DEV_PHONE_CODE` | Auth; fixed development code | Unset; do not activate legacy auth |
| `SNAPTRADE_CONSUMER_KEY` | Broker/portfolio/execution; unset | Unset; broker owner if later activated |
| `SNAPTRADE_CLIENT_ID` | Broker/portfolio/execution; unset | Unset |
| `SNAPTRADE_WEBHOOK_SECRET` | Broker; unset | Unset |
| `SNAPTRADE_CONNECTION_TYPE` | Broker; `read` | Dormant; retain read-only if ever reviewed |
| `IBKR_AUTH_MODE` | IBKR client; `gateway` | Dormant |
| `IBKR_BASE_URL` | IBKR client; localhost gateway or official OAuth URL | Dormant; no local gateway in launch |
| `IBKR_HTTP_TIMEOUT` | IBKR client; `30` | Dormant |
| `IBKR_VERIFY_SSL` | IBKR client; `false` | Unsafe if activated; require true in any future production integration |
| `IBKR_OAUTH_ACCESS_TOKEN` | IBKR client; unset | Unset |
| `IBKR_DEFAULT_EXCHANGE` | IBKR client; `SMART` | Dormant |
| `IBKR_DEFAULT_CURRENCY` | IBKR client; `CHF` | Dormant |
| `IBKR_ORDER_WAIT_TIMEOUT` | IBKR client; `90` | Dormant |
| `IBKR_AUTO_CONFIRM_ORDER_REPLIES` | IBKR client; `false` | Keep false |
| `IBKR_CONID_SGLN` | IBKR client; fixed instrument ID | Dormant; not a credential |
| `IBKR_CONID_SSLN` | IBKR client; fixed instrument ID | Dormant; not a credential |
| `IBKR_CONID_SPLT` | IBKR client; fixed instrument ID | Dormant; not a credential |
| `IBKR_CONID_SPDM` | IBKR client; fixed instrument ID | Dormant; not a credential |
| `AURORATIO_FEE_RESERVE_PERCENT` | IBKR client; `0.5` | Dormant |
| `AURORATIO_EXECUTION_MODE` | Website execution; `dry_run` | Keep disabled/dry_run; do not launch execution service |
| `AURORATIO_ALLOW_LIVE_TRADING` | Website execution; `false` | Explicit false |
| `AURORATIO_SYNC_SNAPTRADE_BEFORE_EXECUTION` | Website execution; `false` | Keep false |
| `AURORATIO_ENABLE_WEBSITE_SCHEDULER` | Legacy scheduler; `false` | Explicit false |
| `AURORATIO_EXECUTION_HOUR` | Legacy scheduler; `17` | Dormant |
| `AURORATIO_EXECUTION_MINUTE` | Legacy scheduler; `5` | Dormant |
| `AURORATIO_EXECUTION_TIMEZONE` | Legacy scheduler; `Europe/Paris` | Dormant; not the active strategy timezone variable |
| `ALERT_EMAIL_FROM` | Legacy Gmail alert sender; unset | Unset unless legacy alert path deliberately used |
| `EMAIL_FROM` | Fallback for preceding setting | Same |
| `ALERT_EMAIL_TO` | Legacy Gmail alert recipient; unset | Same; not a Brevo recipient override |
| `EMAIL_TO` | Fallback for preceding setting | Same; not a subscriber email override |
| `GMAIL_APP_PASSWORD` | Legacy SMTP alert sender; unset | Unset; active transactional email uses Brevo |

Non-executable `backend/services/execution_scheduler.txt` additionally contains `AURORATIO_EXECUTION_DRY_RUN` (true), `AURORATIO_SCHEDULER_ENABLED` (false), `AURORATIO_SCHEDULER_TIMEZONE` (Europe/Paris), `AURORATIO_DAILY_HOUR` (17), and `AURORATIO_DAILY_MINUTE` (5). These are inactive reference code, not launch settings.

`STRIPE_PAYMENT_FAILURE_GRACE_DAYS`, `STRIPE_EVENT_RETRY_SECONDS`, and `STRIPE_EVENT_MAX_ATTEMPTS` appear in tests but are **not read by runtime code**. Runtime values are fixed at 3 days / 300 seconds / 5 attempts respectively. No `CORS_ORIGINS`, `ALLOWED_HOSTS`, `EMAIL_TO_OVERRIDE`, or global sandbox/test-recipient flag is implemented.

## Platform/build settings, distinct from application reads

| Setting | Required handling |
|---|---|
| Railway `PORT` | Platform supplied; use in API/static-server start command, bind `0.0.0.0` |
| Railway database service variables | Preserve existing DB service, credential configuration, storage mount and version. Reference its `DATABASE_URL`; do not rewrite PostgreSQL initialization credentials on an existing volume. Staging needs its own service/volume/credentials. |
| `RAILPACK_SPA_OUTPUT_DIR` | Set `dist` for the proposed frontend static/Caddy build; platform setting, not application code |
| `RAILPACK_NO_SPA` | Leave unset/false so Caddy SPA detection stays enabled |
| `RAILPACK_NODE_VERSION` | Pin a Vite-8-compatible Node version after staging validation; tests need TypeScript support |
| `NODE_ENV` | Production build for both environments; install dev dependencies for TypeScript/Vite build (`npm ci --include=dev`) |
| `PYTHONUNBUFFERED` | Optional `1` for visible worker logs |
| `PYTHONPATH` | No override needed with documented repository-root commands and `--app-dir backend` |
| `FORWARDED_ALLOW_IPS` / Uvicorn proxy flags | Library/server setting; verify Railway proxy trust and real client IP before relying on per-IP rate limits. Do not blindly trust arbitrary public forwarding headers. |
| `RAILWAY_DEPLOYMENT_DRAINING_SECONDS` | Give in-flight requests/background tasks time to finish; Railway default may force immediate termination. Use measured maximum duration, initially at least 60 seconds and verify actual graceful exit. |
| `RAILWAY_DEPLOYMENT_OVERLAP_SECONDS` | Does not replace explicitly stopping old fulfillment senders for this migration; scheduler/removal worker must remain single-instance |
| Railway root/build/start/pre-deploy/healthcheck/cron settings | Dashboard configuration, not repository environment-variable readers; see production-readiness audit |

`backend/.env.example` is incomplete: it omits active JWT, production-mode, contact-recipient, Telegram-webhook and membership-removal settings. Use this inventory, not just that example. Do not place backend secrets in any `VITE_*` variable. Vite substitutes frontend configuration during build: [official environment documentation](https://vite.dev/guide/env-and-mode).
