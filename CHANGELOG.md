# Changelog

All notable changes to dcm-anon-vault are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) — semver.

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
