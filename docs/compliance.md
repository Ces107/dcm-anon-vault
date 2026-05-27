# Compliance crosswalk

Plain-English mapping of the regulatory controls that hospital,
research, and life-sciences customers commonly ask about against the
controls `dcm-anon-vault` implements.

**Honest framing.** Software cannot, by itself, make an organisation
"compliant" — compliance is an organisational property that also
covers people, paper, and process. This document distinguishes:

- **Software-provided** — `dcm-anon-vault` ships this control.
- **Customer-configured** — `dcm-anon-vault` exposes the knob; the
  customer must turn it.
- **Out of scope** — `dcm-anon-vault` cannot help; the customer needs
  another control (legal, organisational, infrastructure).

We never write that the software "guarantees compliance" or is
"certified compliant out of the box." Both are epistemically
incoherent for a piece of code.

## GDPR (Regulation (EU) 2016/679)

| Article | Requirement | Control in `dcm-anon-vault` |
|---------|-------------|------------------------------|
| Art 5(1)(c) — data minimisation | Process only what is necessary. | **Software-provided.** PS3.15 Basic Profile scrubs ~50 PHI tags by default; engine config is opinionated, not à la carte. |
| Art 5(1)(d) — accuracy | Reasonable steps to correct/erase inaccurate data. | **Customer-configured.** Use `POST /v1/admin/retention/sweep` + lower `Customer.retention_days` if a tenant requests early deletion. |
| Art 5(1)(e) — storage limitation | Personal data kept no longer than necessary. | **Software-provided + customer-configured.** `retention_days` column (default 30 d) drives the sweep; customer chooses the value. |
| Art 5(2) + Art 30 — accountability + records of processing | Operator must demonstrate compliance and keep RoPA. | **Software-provided (partial).** Tamper-evident audit chain over every anonymise call (`/v1/audit/verify`); JSON access logs with `request_id` / `tenant` / `route` / `status`. Customer still owns the RoPA document itself. |
| Art 17 — right to erasure | Erase personal data on request. | **Software-provided.** Per-tenant retention sweep + admin endpoint; for one-off deletes hit the DB directly. Note: sweeping breaks the audit chain by design (see `security.md`). |
| Art 25 — data protection by design | Embed safeguards in processing. | **Software-provided.** Default-deny auth, signed webhooks (in and out), strict upload cap, burned-in-PHI refusal, rate-limit per tenant. |
| Art 32 — security of processing | Pseudonymisation, integrity, availability, regular testing. | **Software-provided + customer-configured.** Pseudonymisation = PS3.15 engine; integrity = audit chain; availability = customer's infra; regular testing = `bandit` + `pip-audit` in CI (this repo) + customer pen-tests. |
| Art 33 / 34 — breach notification | Notify supervisory authority / data subjects within 72 h. | **Out of scope.** Process belongs to the operator's DPO. The audit chain helps establish breach scope. |
| Art 28 — processor obligations + DPA | Written contract between controller and processor. | **Out of scope (legal).** Template DPA published separately at `/legal/dpa` (work in progress). |
| EDPB Guidelines 01/2025 — pseudonymisation | Pseudonymised data ≠ anonymous; remains personal data. | **Software-provided.** README and customer-facing copy uses "pseudonymisation" everywhere; no overclaim of anonymisation. |

## HIPAA Technical Safeguards (45 CFR §164.312)

For US Covered Entities. Note: the hosted service is **not currently
offered to US Covered Entities** until a BAA programme is in place
(see README §7). The mapping below applies to self-hosted deployments.

| Standard | Requirement | Control |
|----------|-------------|---------|
| §164.312(a)(1) — access control | Unique user identification + emergency access. | **Customer-configured.** API key per customer; OIDC sub claim per user. Operator must rotate keys / disable accounts. |
| §164.312(a)(2)(iii) — automatic logoff | Terminate session after inactivity. | **Customer-configured.** API keys do not auto-expire; OIDC tokens have IdP-defined TTL. Use OIDC with short TTL for HIPAA deployments. |
| §164.312(a)(2)(iv) — encryption / decryption | Where reasonable and appropriate. | **Customer-configured.** TLS at the proxy (mandatory); DB encryption at rest is operator-provisioned. |
| §164.312(b) — audit controls | Record + examine activity. | **Software-provided.** Tamper-evident audit chain + JSON access logs. Examine via `/v1/audit/verify` + log shipping. |
| §164.312(c)(1) — integrity | Protect ePHI from improper alteration. | **Software-provided.** Audit chain detects retro-edits. Operator must read & alert on `"status":"broken"`. |
| §164.312(d) — person or entity authentication | Verify the person claiming access. | **Software-provided.** API key OR OIDC. OIDC strongly recommended (HIPAA examiners are increasingly assertive about MFA). |
| §164.312(e)(1) — transmission security | Guard against unauthorized access during transmit. | **Customer-configured.** TLS at proxy; HMAC-signed outbound webhooks. |

## EU MDR (Regulation (EU) 2017/745)

`dcm-anon-vault` is **not a medical device** under MDR Art 2(1): it
does not inform clinical diagnosis or therapeutic decisions. The
following are touchpoints if a customer integrates it into a clinical
pipeline (which makes THEM the device manufacturer / system
integrator, not us).

| Article | Requirement | How `dcm-anon-vault` helps |
|---------|-------------|----------------------------|
| Art 10 — technical documentation | Annex II / III file. | **Software-provided documentation.** This `docs/` tree (api.md, security.md, deploy.md, compliance.md, openapi.json) is the kind of evidence Annex II asks for. Customers still need their own DoC. |
| Art 61 — clinical evaluation | Evidence of clinical performance. | **Out of scope.** We do not perform clinical evaluation; pseudonymisation is a pre-processing step, not a clinical claim. |
| Art 89 — post-market surveillance | Track issues, severity, response. | **Software-provided (partial).** GitHub issue tracker + `SECURITY.md` disclosure policy + audit chain integrity alerts. |
| Annex I §17.2 — IT-security | Risk-managed software including for non-MD components. | **Software-provided.** STRIDE model in `security.md`; `bandit` + `pip-audit` in CI; pinned dep upper-bounds. |

## ISO/IEC 27001:2022 (illustrative control mapping)

This is **not** a certification claim. Map to your customer's ISMS
during procurement; pick the controls below to demonstrate evidence.

| Annex A control | What we provide |
|------------------|----------------|
| A.5.7 Threat intelligence | `pip-audit` in CI; subscribe to `dcm-anonymizer` security advisories. |
| A.5.15 Access control | API-key + OIDC, admin role gate. |
| A.5.34 Privacy and protection of PII | Pseudonymisation engine + retention sweep + audit chain. |
| A.8.16 Monitoring activities | JSON access logs + Prometheus `/metrics`. |
| A.8.24 Use of cryptography | TLS at proxy; HMAC-SHA256 for outbound webhooks; SHA-256 for audit chain + API-key hashing. |

## What we do not promise

- No CE-mark, no FDA 510(k), no UKCA, no MFDS, no SAUDI FDA.
- No SOC 2 Type II report. The control set is *designed to support*
  one — the certification belongs to the operating organisation.
- No "HIPAA compliant" / "GDPR compliant" sticker. Compliance is a
  property of your operation, not of any single piece of software.

If a procurement document insists on any of the above, escalate to
the operator (`plusultra.dev@proton.me`); we will tell you honestly
what's in scope and where you need a separate control.
