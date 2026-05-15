# dcm-anon-vault

A hosted, single-tenant DICOM anonymization API. Upload DICOM files over HTTP,
get back a ZIP of anonymized outputs plus a tamper-evident audit log. Stripe
billing is built in for pay-as-you-go tier enforcement.

---

## 1. What it is

dcm-anon-vault wraps the [dcm-anon](https://github.com/plusultra-tools/dcm-anon)
PS3.15 anonymization engine in a FastAPI service. You deploy one instance per
customer (single-tenant), point it at a SQLite volume, and give each customer an
API key. The service enforces per-tier file quotas, logs every anonymization event
with a SHA-256 audit chain, and integrates with Stripe for upgrade billing.

All PHI scrubbing is done by `dcm-anon`, which implements the DICOM PS3.15 Basic
Application Level Confidentiality Profile. No data ever leaves the machine you
deploy on.

---

## 2. Why hosted vs running the CLI locally

| Concern | CLI | Vault (hosted) |
|---------|-----|----------------|
| Audit log retention | You manage the JSON file | Persisted to SQLite, queryable |
| Multi-user access | Manual key sharing | Per-customer API keys + tiers |
| Billing | Manual invoicing | Stripe Checkout built in |
| Deployment | Per-workstation install | Deploy once on Fly.io or your VPS |
| CI integration | Possible but fragile | `POST /v1/anonymize` from any client |

If you process fewer than 50 DICOMs per month, the free tier is sufficient. If you
need auditability across a team, or want to gate access by subscription, the hosted
vault is the right tool.

---

## 3. Tiers

| Tier | Price | Quota | Isolation |
|------|-------|-------|-----------|
| Free | €0/mo | 50 files/month (rate-limited) | Shared single-tenant |
| Pro | €99/mo | Unlimited | Single-tenant (your own deploy) |
| Enterprise | €499/mo | Unlimited | Isolated VPS, dedicated support |

Tier is enforced per API key. Free-tier customers get a `429 Too Many Requests`
with a `Retry-After` header once they hit the monthly cap. Upgrading via Stripe
Checkout flips the tier in the database immediately on webhook receipt.

---

## 4. Deploy in 5 minutes on Fly.io

**Prerequisites:** [flyctl](https://fly.io/docs/hands-on/install-flyctl/) installed
and authenticated.

```bash
# 1. Clone and enter the directory
git clone https://github.com/plusultra-tools/dcm-anon-vault
cd dcm-anon-vault

# 2. Create a new Fly.io app (accept the generated name or set your own)
fly apps create dcm-anon-vault

# 3. Create a persistent volume for SQLite
fly volumes create vault_data --size 1 --region cdg

# 4. Set secrets (never commit these)
fly secrets set \
  DCM_API_KEYS="customer1:$(openssl rand -hex 32)" \
  STRIPE_TEST_KEY="sk_test_REPLACE_ME" \
  STRIPE_PRICE_ID="price_REPLACE_ME" \
  STRIPE_WEBHOOK_SECRET="whsec_REPLACE_ME"

# 5. Deploy
fly deploy

# 6. Smoke-test
curl https://dcm-anon-vault.fly.dev/health
```

**Deployment dependencies:**
- `plusultra.dev@proton.me` email address requires Cloudflare Email Routing to be
  configured before this address is live. Set up at
  https://dash.cloudflare.com → Email → Email Routing.
- Stripe webhooks must point to `https://<your-app>.fly.dev/v1/billing/webhook`
  in the Stripe dashboard under Developers → Webhooks.

---

## 5. API quick reference

```bash
# Anonymize one or more DICOMs (returns ZIP)
curl -X POST https://<host>/v1/anonymize \
  -H "X-API-Key: <your-key>" \
  -F "files=@scan.dcm" \
  --output result.zip

# Start a Stripe Checkout upgrade session
curl -X POST https://<host>/v1/billing/checkout-session \
  -H "X-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"success_url":"https://example.com/success","cancel_url":"https://example.com/cancel"}'
```

---

## 6. Local development

```bash
cp .env.example .env          # fill in values
pip install -e ".[dev]"
uvicorn dcm_anon_vault.app:app --reload --port 8080

# Run tests
python -m pytest -q
python -m ruff check src tests
python -m mypy --strict src
```

---

## 7. Honest disclaimer

**Pre-revenue MVP. We do not yet sign BAAs or DPAs.** Customers must run this
service on their own infrastructure, under their own legal regime and data
processing agreements. We make no HIPAA, GDPR, or MDR compliance claims on your
behalf. The anonymization engine follows DICOM PS3.15 Basic Profile; whether that
satisfies your regulatory obligations is your counsel's determination, not ours.

We anonymize. We audit. We do not promise HIPAA/GDPR-clean by ourselves — that is
the customer's regulator's call.

Contact: plusultra.dev@proton.me (see deployment dependencies above for email setup).

---

Copyright (c) 2026 plusUltra Labs — MIT License
