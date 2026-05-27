# Changelog

All notable changes to dcm-anon-vault are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — semver.

## [0.3.0] — 2026-05-20

Enterprise-grade controls layer. No breaking changes to the existing
API-key + billing path; all additions are opt-in via env vars / new
endpoints.

### Added
- **Tamper-evident audit chain** on `anonymization_events`: each row
  stores `prev_hash` + `row_hash` (SHA-256 over canonical-JSON of the
  prior row's full state). New admin endpoint
  `GET /v1/audit/verify` walks the chain and returns OK or the first
  broken row id. See `docs/security.md` § Audit chain.
- **Per-tenant rate-limiting** middleware (`rate_limit.py`). Fixed-window
  60-s counter; limits taken from `Customer.rate_limit_per_minute`
  override, else `DCM_RATE_LIMIT_<TIER>` env, else built-in tier
  defaults (`free=30/min`, `pro=600/min`, `enterprise=6000/min`). 429
  with `Retry-After` on hit.
- **Prometheus `/metrics`** endpoint exposing
  `anonymize_requests_total{tenant,status}`,
  `anonymize_bytes_processed_total{tenant}`,
  `billing_events_total{tenant,kind}`. Scrape-friendly, no auth (mount
  behind a private network or auth proxy).
- **Structured JSON access logs** via `RequestLogMiddleware` +
  `JsonFormatter`. One line per request with `ts`, `level`,
  `request_id`, `tenant`, `route`, `method`, `status`, `duration_ms`.
  Disable via `DCM_DISABLE_JSON_LOG=1`.
- **Outgoing webhooks** with retries + dead-letter queue.
  `POST /v1/webhooks` registers a URL + secret; on
  `anonymize.completed` the service POSTs a signed payload
  (`X-Webhook-Signature: sha256=<hex>`). 3 attempts (1 s / 5 s / 25 s);
  on final failure a row lands in `webhook_deadletter`, inspectable
  via admin `GET /v1/webhooks/deadletter`.
- **OIDC Bearer-token authentication** as an alternative to API-key.
  Enabled when `OIDC_DISCOVERY_URL` is set; otherwise the API-key path
  remains the sole auth method. `JwksOidcAuthenticator` fetches the
  JWKS, caches keys with 5 min TTL, validates RS256 JWTs.
- **GDPR Art 17 retention sweep**. `Customer.retention_days` (default
  30) drives deletion of expired `AnonymizationEvent` and
  `WebhookDeadletter` rows. Admin endpoint
  `POST /v1/admin/retention/sweep` triggers a per-tenant sweep;
  schedule via cron / k8s CronJob.
- **Admin role gate** via `require_admin` dependency. Admins listed
  in `DCM_ADMIN_KEYS` (comma-separated customer_id values).
- New deps: `prometheus-client`, `python-jose[cryptography]`, `httpx`.
- Documentation: `docs/api.md`, `docs/deploy.md`, `docs/security.md`,
  `docs/compliance.md`, `docs/openapi.json`.

### Changed
- Middleware stack reorder: `RequestLog → APIKey → RateLimit` so the
  rate-limiter can read `request.state.api_key_hash` set by
  `APIKeyMiddleware`.
- `customers` table gains `rate_limit_per_minute` (nullable) and
  `retention_days` (default 30) columns. Existing rows unaffected
  (`create_all` is additive on SQLite + Postgres).
- `anonymization_events` table gains `prev_hash` and `row_hash` columns
  (both 64-char hex). Existing rows: hash chain starts from the next
  insert; running `/v1/audit/verify` against a pre-0.3 dataset will
  flag the first new-format row only.

### Security
- All new endpoints under `/v1/audit/*`, `/v1/webhooks/deadletter`,
  `/v1/admin/*` are admin-gated.
- Webhook signature uses HMAC-SHA256 with per-tenant secret.
- `bandit -r src/` clean (zero HIGH severity issues).

## [0.2.0] — 2026-05-19

### Added
- Real `dcm-anonymizer>=0.4.0` engine wired into `core.py` (replaces the
  earlier placeholder `importlib` stub that pointed at non-existent
  modules).
- `GET /v1/usage` endpoint returning tier, files used MTD, quota, reset
  time.
- Per-customer deterministic UID re-mapping via `UIDMapper(salt=...)`
  using the SHA-256(api_key) as salt — enables longitudinal cohort
  consistency across calls.
- Refusal of files declaring `BurnedInAnnotation == YES` (HTTP 422) —
  the PS3.15 Clean Pixel Data Option is **not** implemented; we refuse
  rather than silently leak burned-in PHI.
- `webhook_events` table for Stripe webhook idempotency.
- Annual SKU support via `STRIPE_PRICE_ID_ANNUAL` and `?plan=annual`.
- Optional Pro trial via `STRIPE_TRIAL_DAYS`.
- Stripe Checkout now collects `customer_email`, `tax_id_collection`,
  `automatic_tax`, `billing_address_collection="required"`.
- WAL journal mode + `synchronous=NORMAL` on SQLite.
- `/health` now performs a real DB SELECT 1 (returns 503 on failure).
- GitHub Actions CI (pytest + ruff + mypy + pip-audit) on push/PR.
- Non-root container user (`app:app`).
- `.env.example`, `NOTICE.md`, `SECURITY.md`, `CHANGELOG.md`.
- Integration test that runs a real pydicom CT_small.dcm through the
  endpoint (no mocked engine).

### Changed
- **API breaking** — Stripe webhook MANDATES `STRIPE_WEBHOOK_SECRET`;
  the previous "skip signature verification if secret unset" fallback
  has been removed. Unsigned events now return 503 / 400.
- README rewritten: "pseudonymization per PS3.15 Basic Profile" instead
  of "anonymization"; tenancy is single-tenant everywhere; §7
  disclaimer is now defensible legal posture rather than a blanket
  liability shield.
- `customers` table: `api_key_hash` now stores `SHA-256(raw_key)`
  (was: the customer_id string). Added `customer_id_string` column.
- Dependency versions pinned (upper bounds): `pydicom>=3.0.2,<4.0`,
  `stripe>=8,<13`, `fastapi>=0.110,<1.0`.
- `STRIPE_TEST_KEY` env var renamed to `STRIPE_API_KEY` (the old name
  still works for backward compatibility).

### Fixed
- Path-traversal in upload filename (`../../etc/passwd`). Sanitised via
  `Path(name).name`.
- Multipart OOM: 100 MB total cap, streamed to disk via 64 KB chunks.
- Race condition in customer creation (`_get_or_create_customer` now
  swallows `IntegrityError` and re-selects).
- `/docs`, `/redoc`, `/openapi.json` are off by default (set
  `DCM_OPEN_DOCS=1` to re-enable). Closes the ePrivacy/cookie-leak
  exposure from the Swagger CDN assets.

### Removed
- The legacy `STRIPE_WEBHOOK_SECRET` "dev-mode fallback" that accepted
  unsigned webhooks (CVE-class issue, see SECURITY.md).
- README claims of HIPAA / GDPR "anonymization" — replaced with
  accurate "pseudonymization" wording and PS3.15 scope.

## [0.1.0] — 2026-05-15

Initial scaffold. Stripe billing, single-tenant API key auth, SQLite
audit log. Engine wiring was a placeholder.
