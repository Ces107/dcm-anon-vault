# API reference

This document lists every HTTP endpoint exposed by `dcm-anon-vault` v0.3.x.
The machine-readable schema lives at [`openapi.json`](./openapi.json)
(also served at `/openapi.json` when `DCM_OPEN_DOCS=1`).

Conventions:

- All paths starting with `/v1/` require authentication.
- Authentication is either `X-API-Key: <key>` (default) or
  `Authorization: Bearer <jwt>` when OIDC is enabled (`OIDC_DISCOVERY_URL`).
- All requests/responses use JSON unless noted. Multipart upload is used
  only by `POST /v1/anonymize`.
- Admin endpoints additionally require the calling customer's id to be
  in `DCM_ADMIN_KEYS` (comma-separated allowlist).

## Health and observability

### `GET /health`

Open. Returns 200 if the database is reachable.

```bash
curl https://your-host/health
# {"status":"ok","version":"0.3.0"}
```

503 with `{"detail":"Database unavailable"}` if `SELECT 1` fails.

### `GET /metrics`

Open. Prometheus exposition format. Counters:

- `anonymize_requests_total{tenant,status}`
- `anonymize_bytes_processed_total{tenant}`
- `billing_events_total{tenant,kind}`

```bash
curl https://your-host/metrics | head -20
```

Mount behind a private network or auth proxy in production.

## Core

### `POST /v1/anonymize`

Multipart upload (`files=`). Returns a ZIP archive of pseudonymized
DICOMs.

```bash
curl -X POST https://your-host/v1/anonymize \
  -H "X-API-Key: $KEY" \
  -F "files=@scan1.dcm" \
  -F "files=@scan2.dcm" \
  --output result.zip
```

Response headers:

- `Content-Disposition: attachment; filename=anonymized.zip`
- `X-Files-Processed: <n>`
- `X-Files-Failed: <n>`
- `X-Files-Rejected-BurnedIn: <n>`
- `X-Audit-Sha256: <hex>` — engine audit hash (PS3.15 record digest)
- `X-Request-Id: <hex>` — correlated to JSON access logs

Status codes:

- `200` — success.
- `401` — missing/invalid key.
- `413` — payload > 100 MB cap.
- `422` — every file rejected due to `BurnedInAnnotation=YES`.
- `429` — free-tier monthly quota exhausted OR per-tenant rate limit.

### `GET /v1/usage`

Returns the calling customer's tier, files used MTD, monthly quota, and
the reset timestamp.

```bash
curl https://your-host/v1/usage -H "X-API-Key: $KEY"
# {"tier":"free","files_used_mtd":12,"quota":50,"reset_at":"2026-06-01T00:00:00+00:00"}
```

## Billing (Stripe)

### `POST /v1/billing/checkout-session`

Body:

```json
{
  "success_url": "https://example.com/success",
  "cancel_url": "https://example.com/cancel",
  "plan": "monthly",
  "customer_email": "buyer@example.com"
}
```

`plan` is `"monthly"` (default) or `"annual"`. Returns:

```json
{"checkout_url": "https://checkout.stripe.com/...", "session_id": "cs_..."}
```

503 if Stripe is not configured (missing `STRIPE_API_KEY` or
`STRIPE_PRICE_ID`).

### `POST /v1/billing/webhook`

Stripe-signed webhook. The service refuses unsigned events (503 if
`STRIPE_WEBHOOK_SECRET` is unset or the placeholder; 400 if signature
invalid). Currently handles `checkout.session.completed` (flips tier
to `pro` and stores the Stripe customer id).

## Outgoing webhooks

### `POST /v1/webhooks`

Register a URL to receive `anonymize.completed` events.

```bash
curl -X POST https://your-host/v1/webhooks \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://customer.example/hook","secret":"super-secret-shared"}'
```

Returns `{"id": 1, "url": "...", "active": true, "created_at": "..."}`.

### `GET /v1/webhooks`

List the calling customer's registered webhook URLs.

### `GET /v1/webhooks/deadletter`  *(admin)*

Returns up to 1000 deadlettered delivery rows (3-strikes failures).

```bash
curl https://your-host/v1/webhooks/deadletter?limit=50 -H "X-API-Key: $ADMIN_KEY"
```

### Payload signing

Outgoing webhook bodies are signed with HMAC-SHA256 using the
registered secret:

```
X-Webhook-Signature: sha256=<hex>
```

Verify on the receiver side:

```python
import hmac, hashlib
expected = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
assert hmac.compare_digest(expected, request.headers["X-Webhook-Signature"])
```

Retries: 3 attempts, backoff 1 s / 5 s / 25 s. On final failure a row
is written to `webhook_deadletter`.

## Audit chain

### `GET /v1/audit/verify` *(admin)*

Walks the `anonymization_events` hash chain. Returns:

```json
{"status": "ok", "first_broken_id": null}
```

or, on tampering:

```json
{"status": "broken", "first_broken_id": 42}
```

## Retention (GDPR Art 17)

### `POST /v1/admin/retention/sweep` *(admin)*

Deletes `AnonymizationEvent` + `WebhookDeadletter` rows older than each
tenant's `retention_days` value (default 30). Idempotent. Schedule via
cron or a k8s CronJob:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata: { name: dcm-vault-retention }
spec:
  schedule: "17 3 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: curl
            image: curlimages/curl:8
            args: ["-fsSL", "-X", "POST", "-H", "X-API-Key: $(KEY)",
                   "http://dcm-vault/v1/admin/retention/sweep"]
            envFrom: [{ secretRef: { name: dcm-vault-admin } }]
          restartPolicy: OnFailure
```

Returns per-tenant counts:

```json
{
  "swept": 2,
  "rows": [
    {"customer_id": 1, "retention_days": 30, "events_deleted": 12, "deadletter_deleted": 0},
    {"customer_id": 2, "retention_days": 90, "events_deleted": 0, "deadletter_deleted": 3}
  ]
}
```

Note: sweeping breaks the audit hash chain by design (oldest surviving
row becomes the new chain root). Run `/v1/audit/verify` BEFORE sweeping
if you need to prove integrity for the about-to-be-deleted range.

## Rate limits

Per-tenant fixed-window 60 s counter. Limits are taken from this order:

1. `Customer.rate_limit_per_minute` DB column (if > 0).
2. `DCM_RATE_LIMIT_<TIER>` env var (e.g. `DCM_RATE_LIMIT_FREE=120`).
3. Built-in tier defaults: `free=30/min`, `pro=600/min`,
   `enterprise=6000/min`.

On hit, the response is 429 with `Retry-After: <s>`.

`/health`, `/metrics`, `/v1/billing/webhook`, `/docs`, `/redoc`,
`/openapi*` are exempt.
