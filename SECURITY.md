# Security Policy

## Reporting a vulnerability

Email **plusultra.dev@proton.me** with the subject prefix
`[SECURITY] dcm-anon-vault:` and a description of the issue.

Please do **not** open a public GitHub issue for suspected
vulnerabilities. We aim to acknowledge within 72 hours and to issue a
fix or mitigation within 30 days.

## Supported versions

This project is pre-1.0; only the `main` branch is supported. Pin a
specific commit hash if you operate it in production.

## Threat model (current)

- **In scope.** API key brute-force, DICOM upload path traversal,
  multipart denial-of-service, Stripe webhook forgery, SQL injection,
  burned-in PHI leak via the response ZIP.
- **Out of scope (today).** Database-at-rest encryption — the audit
  log is not encrypted at rest. See README §7 — this is a research
  utility, not yet a hardened production vault. Customers requiring
  encryption-at-rest must self-host on an encrypted volume
  (LUKS / EBS-KMS / Fly encrypted volumes when generally available)
  AND substitute `DCM_DB_URL` with a Postgres+TDE instance.

## Disclosure

We will publish a coordinated disclosure once a fix ships, with a
`CVE` requested through GitHub Security Advisories when severity
warrants. Researchers are credited in `CHANGELOG.md`.

## Hardening checklist (deployment)

1. `STRIPE_WEBHOOK_SECRET` MUST be set to a real secret (never the
   placeholder `whsec_REPLACE_ME`). The service refuses to process
   unsigned webhooks.
2. `DCM_API_KEYS` keys MUST be at least 32 hex chars
   (`openssl rand -hex 32`).
3. `DCM_OPEN_DOCS=0` in production (default). Open `/docs` only over
   a private network or behind basic auth.
4. Run the container as the non-root `app` user — already the default
   in the bundled Dockerfile.
5. Pin the image digest (`@sha256:...`) in Fly machines / Kubernetes
   manifests.
