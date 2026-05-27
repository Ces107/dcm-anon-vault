# dcm-anon-vault — End-to-end demo

A reproducible transcript of one DICOM file going through the hosted API:
authentication, pseudonymization, audit chain, usage quota, and the
billing flow. All command output below was captured against a real
`uvicorn` instance on `127.0.0.1:8081`; nothing is mocked.

To re-run this on your own machine:

```bash
pip install -e ".[dev]"
python scripts/make_demo_dicom.py demo/sample_with_phi.dcm

DCM_API_KEYS="demo-customer:demo-api-key-not-secret-just-for-docs-PHkjQ8ZxLm" \
DCM_ADMIN_KEYS="demo-customer" \
DCM_DB_URL="sqlite:///./demo/demo-vault.db" \
DCM_AUDIT_DIR="./demo/audit" \
python -m uvicorn dcm_anon_vault.app:app --port 8081
```

Then `curl` the endpoints below from a second shell.

---

## 0. Generate a sample DICOM with populated PHI

`scripts/make_demo_dicom.py` adapts the `CT_small.dcm` shipped with
`pydicom` and overwrites the patient-identifying tags with recognisable
fake values so the scrubbing is obvious:

```
PatientName       : DEMO^Jane
PatientID         : DEMO-PATIENT-001
PatientBirthDate  : 19800101
ReferringPhysician: SMITH^John
Institution       : Demo Hospital Madrid
StudyDescription  : Demo abdominal CT for dcm-anon-vault docs
AccessionNumber   : ACC-2026-0001
StudyInstanceUID  : 1.3.6.1.4.1.5962.1.2.1.20040119072730.12322
SOPInstanceUID    : 1.3.6.1.4.1.5962.1.1.1.1.1.20040119072730.12322
```

## 1. Health check

```bash
$ curl -s http://127.0.0.1:8081/health
{"status":"ok","version":"0.3.0"}
```

## 2. Anonymize one file

```bash
$ curl -s -D - -o demo/result.zip \
    -X POST http://127.0.0.1:8081/v1/anonymize \
    -H "X-API-Key: demo-api-key-not-secret-just-for-docs-PHkjQ8ZxLm" \
    -F "files=@demo/sample_with_phi.dcm"
```

Response headers captured verbatim:

```
HTTP/1.1 200 OK
content-disposition: attachment; filename=anonymized.zip
x-files-processed: 1
x-files-failed: 0
x-files-rejected-burnedin: 0
x-audit-sha256: 579c78206b8f53cdf1260ee74957d4c62d890b0e985f958605d7d9271f0f4e96
content-length: 25316
content-type: application/zip
x-request-id: ddd3f22d24bb46a2
```

`x-audit-sha256` is the hash recorded in the audit chain for this call.
`x-request-id` is the correlation id you will see in the access log.

## 3. Inspect the scrubbed output

The returned zip contains the pseudonymized DICOM under `out/`:

```
demo/result.zip
└── out/sample_with_phi.dcm   38916 bytes
```

Tag-by-tag diff between input and output (run with the helper at the
end of `scripts/make_demo_dicom.py` or any DICOM viewer):

| Tag                       | Input                                      | Output                                  |
|---------------------------|--------------------------------------------|-----------------------------------------|
| PatientName               | `'DEMO^Jane'`                              | `'ANON'`                                |
| PatientID                 | `'DEMO-PATIENT-001'`                       | `'0'`                                   |
| PatientBirthDate          | `'19800101'`                               | `'19000101'`                            |
| ReferringPhysicianName    | `'SMITH^John'`                             | `''` (cleared)                          |
| InstitutionName           | `'Demo Hospital Madrid'`                   | `''` (cleared)                          |
| StudyDescription          | `'Demo abdominal CT for dcm-anon-vault…'`  | `''` (cleared)                          |
| AccessionNumber           | `'ACC-2026-0001'`                          | `''` (cleared)                          |
| SOPInstanceUID            | `1.3.6.1.4.1.5962.1.1.1.1.1.20040119072…`  | `2.25.544243826543649187543291941998888…`|
| StudyInstanceUID          | `1.3.6.1.4.1.5962.1.2.1.20040119072730.…`  | `2.25.1116774253602043340137466276891…`  |

UIDs are remapped through the `2.25.<UUID-as-int>` form so the
re-identification chain in the source institution is broken while the
Study/Series/SOP relationships across files of the same study remain
coherent.

## 4. Check usage and remaining quota

```bash
$ curl -s http://127.0.0.1:8081/v1/usage \
    -H "X-API-Key: demo-api-key-not-secret-just-for-docs-PHkjQ8ZxLm"
{"tier":"free","files_used_mtd":1,"quota":50,"reset_at":"2026-06-01T00:00:00+00:00"}
```

After two more calls (using `sample_2.dcm` and `sample_3.dcm` as copies
of the same input — UIDs deterministic per API key, so they collapse):

```bash
$ curl -s http://127.0.0.1:8081/v1/usage \
    -H "X-API-Key: demo-api-key-not-secret-just-for-docs-PHkjQ8ZxLm"
{"tier":"free","files_used_mtd":3,"quota":50,"reset_at":"2026-06-01T00:00:00+00:00"}
```

Free tier quota exhaustion returns `429 Too Many Requests` with a
`Retry-After` header and an `X-Upgrade-URL` hint (the path through
`/v1/anonymize` past 50 files in a month is covered by
`tests/test_anonymize_route.py::test_free_tier_quota_returns_429`).

## 5. Verify the audit chain

`GET /v1/audit/verify` walks every row of the audit log and recomputes
the SHA-256 chain. Returns the first row id where the chain breaks,
or `null` if the chain is intact. Requires admin role
(`DCM_ADMIN_KEYS` allow-list):

```bash
$ curl -s http://127.0.0.1:8081/v1/audit/verify \
    -H "X-API-Key: demo-api-key-not-secret-just-for-docs-PHkjQ8ZxLm"
{
    "status": "ok",
    "first_broken_id": null
}
```

A non-admin caller gets `403 Admin role required`.

The chain links each row to its predecessor via
`row_hash = sha256(canonical_json(this_row, prev_hash))`. Any retroactive
edit of an audit row makes every subsequent `row_hash` wrong and
`first_broken_id` will point at the tampered row. This is what makes the
audit log defensible against a procurement officer who asks "and how do
we know the operator didn't alter the trail after the fact".

## 6. Billing — checkout when Stripe is not yet configured

The service refuses to silently fall back. With no Stripe keys set,
the checkout endpoint returns `503` with an explicit reason:

```bash
$ curl -s -X POST http://127.0.0.1:8081/v1/billing/checkout-session \
    -H "X-API-Key: demo-api-key-not-secret-just-for-docs-PHkjQ8ZxLm" \
    -H "Content-Type: application/json" \
    -d '{"success_url":"https://example.com/ok","cancel_url":"https://example.com/cancel"}'
{"detail":"Stripe is not configured on this instance. Set STRIPE_API_KEY, STRIPE_PRICE_ID and STRIPE_WEBHOOK_SECRET."}
HTTP_STATUS=503
```

With real keys set, the response is a `{"checkout_url": "...", "session_id": "..."}` object that points at a hosted Stripe Checkout
page with a 14-day Pro trial enabled. The same applies to
`POST /v1/billing/portal-session`, which issues a short-lived link to
the Stripe Customer Portal for self-service cancellation. Both flows
are covered end-to-end (with the Stripe SDK mocked) by
`tests/test_billing.py` — `TestCheckoutSession`, `TestPortalSession`,
`TestSubscriptionLifecycle`.

## 7. What this demo does NOT exercise

- **Webhook signature verification.** Mandatory in production; the
  service refuses unsigned events with `503`. Tested in
  `TestWebhook::test_503_when_webhook_secret_unset`.
- **`customer.subscription.deleted` and `customer.subscription.updated`**
  webhook handlers (covered by `TestSubscriptionLifecycle`).
- **OIDC authentication** (`require_oidc_or_api_key`). Tested in
  `tests/test_oidc.py`.
- **Outgoing webhooks with retries / dead-letter**
  (`tests/test_webhook_delivery.py`).
- **GDPR Art. 17 retention sweep**
  (`tests/test_retention.py`).
- **Burned-in pixel PHI rejection** with `BurnedInAnnotation==YES`
  (`tests/test_integration_real_dicom.py::test_burned_in_phi_is_rejected`).

The full pytest suite is 78 tests; everything in this demo is exercised
in the suite at every commit.
