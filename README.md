# dcm-anon-vault

A hosted, single-tenant DICOM **pseudonymization** API. Upload DICOM
files over HTTP, get back a ZIP of pseudonymized outputs plus a
tamper-evident audit log. Stripe billing is built in for pay-as-you-go
tier enforcement.

Free tier: 50 files/mo. Pro: €99/mo (10K files). Annual: €999.
`pip install -e ".[dev]"` then `uvicorn dcm_anon_vault.app:app`.
Enterprise: OIDC, per-tenant rate limits, tamper-evident audit chain,
GDPR Art 17 retention policies, Prometheus metrics, signed outbound
webhooks. See `docs/security.md` and `docs/compliance.md`.

## What's new in 0.3

- Tamper-evident audit hash chain + `GET /v1/audit/verify`.
- Per-tenant rate limiting (429 + `Retry-After`).
- Prometheus `/metrics` endpoint.
- Structured JSON access logs with `request_id` / `tenant` / `duration_ms`.
- Outgoing webhook delivery with retries + dead-letter queue.
- OIDC Bearer-token auth (alternative to API-key, optional).
- GDPR Art 17 retention sweep (per-tenant `retention_days`).
- See `CHANGELOG.md` for the full list.

> **Wording note:** In DICOM and clinical-research practice the
> process is colloquially called "anonymization" (and the upstream
> engine ships as `dcm-anonymizer`). Under EU GDPR (Recital 26 + WP29
> Opinion 05/2014 + EDPB Guidelines 01/2025) the OUTPUT of PS3.15 Basic
> Profile is **pseudonymized** personal data, NOT anonymized. We use
> "pseudonymization" throughout this README and in all customer-facing
> copy; "anonymize" appears only as the technical verb on DICOM tags.

---

## 1. What it is

`dcm-anon-vault` wraps the [`dcm-anonymizer`](https://github.com/Ces107/dcm-anon)
engine (PS3.15 Basic Confidentiality Profile, PyPI:
[`dcm-anonymizer`](https://pypi.org/project/dcm-anonymizer/)) in a
FastAPI service. You deploy one instance per customer (single-tenant),
point it at a SQLite volume, and give each customer an API key. The
service enforces per-tier file quotas, logs every pseudonymization
event with a SHA-256 audit chain, and integrates with Stripe for
upgrade billing.

All PHI scrubbing is done by `dcm-anonymizer`, which implements the
DICOM PS3.15 Basic Application Level Confidentiality Profile. No data
ever leaves the machine you deploy on.

UID re-mapping is **deterministic per customer** (we use
`SHA-256(api_key)` as the engine salt), so re-running the same source
study produces the same target SOPInstanceUID / PatientID. This enables
longitudinal cohort linkage that random UIDs would destroy.

---

## 2. Why hosted vs running the CLI locally

| Concern | CLI (`pip install dcm-anonymizer`) | Vault (hosted) |
|---------|-----|----------------|
| Audit log retention | You manage the JSON file | Persisted to SQLite, queryable |
| Multi-user access | Manual key sharing | Per-customer API keys + tiers |
| Billing | Manual invoicing | Stripe Checkout built in |
| Deployment | Per-workstation install | Deploy once on Fly.io or your VPS |
| CI / pipeline integration | Possible but fragile | `POST /v1/anonymize` from any client |

If you process fewer than 50 DICOMs per month, the free tier is
sufficient. If you need auditability across a team, or want to gate
access by subscription, the hosted vault is the right tool.

---

## 3. Tiers (subject to change pre-1.0)

| Tier | Price | Quota | Isolation |
|------|-------|-------|----------|
| Free | €0/mo | 50 files/month | Shared single-tenant |
| Pro  | €99/mo | Fair-use 10K files/mo | Single-tenant (your own deploy) |
| Annual | €999/yr | Fair-use 10K files/mo | Same as Pro; ~17 % off |
| Enterprise | Contact | SLA, BAA, async jobs, SSO | Isolated VPS, dedicated support |

Free-tier customers receive `429 Too Many Requests` with a `Retry-After`
header once they hit the monthly cap. Upgrading via Stripe Checkout
flips the tier in the database on signed-webhook receipt.

A 14-day Pro trial is enabled by default (`STRIPE_TRIAL_DAYS=14`).

---

## 4. Deploy in 5 minutes on Fly.io

**Prerequisites:** [flyctl](https://fly.io/docs/hands-on/install-flyctl/)
installed and authenticated.

```bash
git clone https://github.com/Ces107/dcm-anon-vault
cd dcm-anon-vault

fly apps create dcm-anon-vault
fly volumes create vault_data --size 1 --region cdg

fly secrets set \
  DCM_API_KEYS="customer1:$(openssl rand -hex 32)" \
  STRIPE_API_KEY="sk_test_REPLACE_ME" \
  STRIPE_PRICE_ID="price_REPLACE_ME" \
  STRIPE_PRICE_ID_ANNUAL="price_REPLACE_ME" \
  STRIPE_WEBHOOK_SECRET="whsec_REAL_SECRET_HERE"

fly deploy
curl https://dcm-anon-vault.fly.dev/health
```

**Required Stripe configuration before any paid customer:**
- Monthly price → `STRIPE_PRICE_ID`.
- Optional annual price → `STRIPE_PRICE_ID_ANNUAL`.
- Webhook endpoint at `https://<your-app>/v1/billing/webhook` pointing
  at the events: `checkout.session.completed`. Copy the signing
  secret into `STRIPE_WEBHOOK_SECRET`. The service refuses to
  process unsigned events.

---

## 5. API quick reference

```bash
# Pseudonymize one or more DICOMs (returns ZIP)
curl -X POST https://<host>/v1/anonymize \
  -H "X-API-Key: <your-key>" \
  -F "files=@scan.dcm" \
  --output result.zip

# Check usage / quota for the current UTC month
curl https://<host>/v1/usage -H "X-API-Key: <your-key>"

# Start a Stripe Checkout upgrade (monthly or annual)
curl -X POST https://<host>/v1/billing/checkout-session \
  -H "X-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "success_url":"https://example.com/success",
    "cancel_url":"https://example.com/cancel",
    "plan":"annual",
    "customer_email":"buyer@example.com"
  }'
```

Response headers from `/v1/anonymize` carry `X-Files-Processed`,
`X-Files-Failed`, `X-Files-Rejected-BurnedIn`, and `X-Audit-Sha256`.

---

## 6. Local development

```bash
cp .env.example .env          # fill in real values
pip install -e ".[dev]"
uvicorn dcm_anon_vault.app:app --reload --port 8080

python -m pytest -q
python -m ruff check src tests
python -m mypy --strict src
```

---

## 7. Scope, disclaimers, regulatory posture

**This is a research utility. It is NOT a medical device.**

`dcm-anon-vault` is intended for the preparation of DICOM datasets for
research, software development, and educational use. It is **not**
intended to inform clinical diagnosis or therapeutic decisions and is
**not** a medical device under Regulation (EU) 2017/745 (MDR) Art 2(1)
nor under 21 CFR Part 820. If you intend to use it as a pre-processing
step in a clinical pipeline, the obligation to perform conformity
assessment falls on you as the deployer / modifier.

**GDPR posture.** PS3.15 Basic Profile is a *pseudonymization*
operation, not anonymization, per EDPB Guidelines 01/2025 on
Pseudonymisation and WP29 Opinion 05/2014. Output remains personal
data and must be handled accordingly. The hosted plane **receives and
briefly processes raw PHI on the customer's behalf**, which makes the
operator a processor under GDPR Art 4(8). A Data Processing Agreement
(DPA) is required before any EU customer can be onboarded; we publish
a template DPA at `/legal/dpa` (work in progress).

**HIPAA posture.** Receiving raw DICOM from a US Covered Entity makes
the operator a Business Associate by operation of law (45 CFR 160.103),
regardless of contract. Until a BAA programme is in place, **the
hosted service is not available to US Covered Entities.** Self-host
the service inside your own HIPAA-compliant environment instead.

**Storage at rest.** The audit log is stored in SQLite **without
disk-level encryption**. Customers requiring encryption-at-rest should
deploy on an encrypted volume (LUKS, KMS-backed EBS, Fly encrypted
volumes) and / or substitute Postgres with TDE via `DCM_DB_URL`.

**What this software does NOT do.** No burned-in pixel-data PHI
removal; we reject files declaring `BurnedInAnnotation==YES` with HTTP
422 rather than silently leak PHI. No SR (Structured Report) text-item
deep redaction (only the engine's PS3.15 actions). No IHE BIR / ATNA
audit message emission. No KMS-backed encryption. No Conformance
Statement (PS3.4 §2.2). Write to us if you need one for a hospital
procurement evaluation.

This README is the canonical scope statement. Marketing copy MUST
match it.

Contact: plusultra.dev@proton.me · Issues:
https://github.com/Ces107/dcm-anon-vault/issues

---

Copyright © 2026 César Pereiro García. MIT License. See `NOTICE.md`
for upstream attribution; `SECURITY.md` for vulnerability reporting;
`CHANGELOG.md` for release history.
