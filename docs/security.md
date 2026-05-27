# Security model

This document captures the threat model, trust boundaries, and the
controls `dcm-anon-vault` provides. Vendor-procurement-friendly; pair
with `compliance.md` for the regulatory crosswalk.

## Trust boundaries

```
┌──────────────────┐  HTTPS  ┌─────────────────────────────┐
│  Customer client │ ───────▶│  Reverse proxy (nginx/Fly)  │
└──────────────────┘         └─────────────┬───────────────┘
                                           │ HTTP (loopback)
                              ┌────────────▼────────────┐
                              │  dcm-anon-vault (FastAPI)│
                              ├──────────────────────────┤
                              │  middleware:             │
                              │   - RequestLog (JSON)    │
                              │   - APIKey / OIDC        │
                              │   - RateLimit (per-tenant)│
                              ├──────────────────────────┤
                              │  routes:                  │
                              │   /v1/anonymize           │
                              │   /v1/usage               │
                              │   /v1/billing/*           │
                              │   /v1/webhooks*           │
                              │   /v1/audit/verify  (admin)│
                              │   /v1/admin/* (admin)     │
                              └─────────────┬────────────┘
                                            │
                              ┌─────────────▼────────────┐
                              │  SQLite or Postgres       │
                              │  (Customer · Audit chain) │
                              └──────────────────────────┘
```

Trust zones:

- **Untrusted** — anything outside the reverse proxy. PHI arrives here.
- **Tenant** — authenticated as a specific `customer_id`. Cannot see
  other tenants' rows.
- **Admin** — listed in `DCM_ADMIN_KEYS`. Can call `/v1/audit/verify`,
  `/v1/webhooks/deadletter`, `/v1/admin/retention/sweep`.

## STRIDE threat model

| Threat | Surface | Mitigation |
|--------|---------|------------|
| **Spoofing** | Inbound API requests | `X-API-Key` SHA-256 hash compare (constant-time) OR OIDC JWT validated against JWKS. |
| **Spoofing** | Inbound Stripe webhook | `STRIPE_WEBHOOK_SECRET`; refuses unsigned events (no dev fallback). |
| **Spoofing** | Outbound webhook to customer | `X-Webhook-Signature` HMAC-SHA256 with per-tenant secret. |
| **Tampering** | Audit log | `prev_hash` + `row_hash` chain over canonical-JSON of every row; `/v1/audit/verify` walks the chain. |
| **Tampering** | Upload filename path traversal | `Path(name).name` sanitisation; bytes streamed to a fresh tempdir, dest path computed from sanitised name only. |
| **Repudiation** | "I didn't process that file" | Audit row per request keyed by tenant + `audit_sha256` (the engine's own PS3.15 digest) + chain prev_hash. |
| **Information disclosure** | PHI in logs | JSON access log emits route + status + duration, NOT request body. Application logs use opaque ids (`request_id`, `audit_sha256` prefix). |
| **Information disclosure** | DB at rest | Out of scope by default — deploy on an encrypted volume (LUKS, KMS-backed EBS, Fly encrypted volumes) or substitute Postgres with TDE. |
| **DoS — single tenant** | High request rate | Per-tenant fixed-window rate limit (60 s); 429 + `Retry-After`. |
| **DoS — large upload** | 100 GB POST | 100 MB hard cap, streamed to disk in 64 KB chunks; reject early via `Content-Length`. |
| **DoS — slowloris-style** | Long-lived connections | Out of scope of the application; configure on the reverse proxy (nginx `client_body_timeout`, Fly proxy default). |
| **Elevation of privilege** | Tenant promotes self to admin | Admin gate compares `customer_id` against `DCM_ADMIN_KEYS` env, which is operator-controlled. Tenants cannot set env. |
| **Elevation of privilege** | Tenant reads another tenant's audit | Every query filters on `customer_id`; no cross-tenant endpoints. Chain verification is admin-only and returns only the `id` of the broken row, not its content. |

## Authentication

### API key (default)

- Configured via `DCM_API_KEYS` env (`id1:key1,id2:key2`).
- Server stores only SHA-256(key) — the raw key is never persisted.
- Validation: SHA-256 lookup + constant-time compare with `hmac.compare_digest`.
- Rotation: add the new pair, deploy, then remove the old pair.

### OIDC Bearer (optional)

- Enabled by setting `OIDC_DISCOVERY_URL`.
- Validates RS256-signed JWTs against the discovered JWKS.
- Optional `OIDC_AUDIENCE` / `OIDC_ISSUER` strict checks.
- `sub` claim → `customer_id`; optional `tenant` claim → tenant scope.
- JWKS cached in-process with 5 min TTL.

### OIDC vs API-key tradeoffs

| Concern | API-key | OIDC |
|---------|---------|------|
| Setup effort | trivial | requires an IdP (Keycloak / Azure AD / Okta / Google) |
| Rotation cadence | manual, infrequent | short-lived tokens, automatic |
| Revocation | redeploy env | revoke session at IdP |
| MFA | no | yes (IdP enforces) |
| Auditability | static identity | per-session, per-MFA-event |
| Hospital procurement | "good enough for pilot" | usually mandatory |

We recommend OIDC for any deployment that needs to satisfy a
procurement questionnaire from a hospital IT department.

## Audit chain

Each row in `anonymization_events` stores:

- `prev_hash` — `row_hash` of the previous row (genesis = 64 zeros).
- `row_hash` — `sha256(canonical_json({id, customer_id, file_count,
  audit_sha256, created_at, prev_hash}))`.

Properties:

- **Append-only by convention.** The DB layer does not enforce it
  (your DBA can DELETE), but the chain verifier (`/v1/audit/verify`)
  will detect any retro-edit.
- **Global chain** (not per-tenant). An attacker who rewrites one
  tenant's history breaks the chain at that point regardless of
  whether their tenant was the most recent writer.
- **No external timestamp authority.** The chain proves **order** and
  **immutability since each write**, not absolute wall-clock time.
  RFC 3161 timestamping is a future option.
- **Retention interaction:** the daily retention sweep DOES break the
  chain by design (oldest surviving row becomes the new chain head).
  Operators should run `/v1/audit/verify` BEFORE a sweep if they need
  to prove integrity for the about-to-be-deleted range, and snapshot
  the result (sign with operator-side key, store off-host).

## Rate limit & DoS posture

- Per-tenant fixed-window 60 s counter, in-process.
- Default limits: `free=30/min`, `pro=600/min`, `enterprise=6000/min`.
  Override per tenant via `Customer.rate_limit_per_minute`, per tier
  via `DCM_RATE_LIMIT_<TIER>` env.
- Multi-worker deployments share neither the counter nor the windows
  (each Uvicorn worker has its own). For strict cluster-wide limits,
  put a Redis-backed limiter at the edge (nginx `limit_req`, Cloudflare
  rate-limit rules, or substitute the in-process limiter with a Redis
  implementation — interface seam in `rate_limit.py`).
- Above the per-tenant limit, the **upload size cap (100 MB)** is the
  next layer of defence; above that, the reverse proxy's body-size
  limit; above that, the cloud provider's DDoS protection.

## Secret handling

- All secrets in env vars: `DCM_API_KEYS`, `STRIPE_*`, `OIDC_*`,
  `DCM_DB_URL`. None are ever read from the DB or logged.
- `STRIPE_WEBHOOK_SECRET = "whsec_REPLACE_ME"` (the README placeholder)
  is explicitly treated as unset (503 on inbound webhook).
- Webhook secrets for outgoing delivery ARE stored in
  `outgoing_webhooks.secret`. Operators using a hardened deploy should
  treat the DB as sensitive material (encryption at rest +
  least-privilege DB user).

## Reporting

See [`SECURITY.md`](../SECURITY.md) for the vulnerability disclosure
policy and contact.

## What this software does NOT do

Honest scope statement; we'd rather you find out from this file than
discover it during a procurement audit:

- **No KMS-backed encryption at rest.** Deploy on encrypted storage.
- **No SAML.** OIDC only (covers most modern EU hospital IdPs).
- **No IHE BIR / ATNA audit message emission.** Audit chain is JSON in
  the DB; if you need ATNA, write an exporter against
  `GET /v1/audit/verify` data.
- **No DICOM Conformance Statement (PS3.4 §2.2).** Engine implements
  PS3.15 actions only; we don't claim PS3.4 conformance. Available on
  request for procurement evaluation.
- **No multi-tenant DB isolation.** Single-tenant by design (one
  deployment per customer); the `customer_id` column is for billing
  granularity, not security isolation against other customers' deploys.
- **No HSM integration for chain anchoring.** RFC 3161 + HSM signing
  is on the 0.4 roadmap if a customer requires it.
- **No SOC2 / ISO 27001 certification.** The software is designed to
  *help* customers meet these — see `compliance.md` for the control
  crosswalk. Certification is on the operator's organisation, not the
  code.
