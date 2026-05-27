# Pricing — dcm-anon-vault

**Last updated:** 2026-05-27. Tiers below are stable until 2026-08-01.

## Tiers

| Tier | Price | Monthly quota | Best for |
|------|-------|---------------|----------|
| **Free** | €0 / month | 50 DICOM files / month, shared rate limit, 30-day audit retention | Evaluation, small research jobs, individual workstations |
| **Pro** | €99 / month | Fair-use 10,000 files / month, dedicated API key, 1-year audit retention, `/metrics` endpoint, webhook delivery | Radiology AI startups, clinical research data leads, pilot deployments |
| **Annual** | €999 / year | Same as Pro, paid annually (≈17 % off) | Teams committed for a year of evaluation work |
| **Enterprise** | from €1,200 / month (contract) | OIDC SSO, per-tenant rate limits, BAA / DPA on file, tamper-evident audit chain with 6-year retention, dedicated support, SLA | Hospital groups, multi-site deployments, GxP environments |

Pro / Annual quota of 10,000 files / month is a fair-use cap. Customers approaching it receive an email nudge and an offered upgrade conversation; no automatic overage is billed.

A **14-day Pro trial** is enabled by default through Stripe Checkout (`STRIPE_TRIAL_DAYS=14`). Start a trial via the checkout endpoint described in the README §5. No separate trial-signup endpoint is required.

## What's included in every paid tier

- The dcm-anon-vault REST API (single-tenant container or per-customer hosted instance).
- PS3.15 Basic Confidentiality Profile pseudonymization via the upstream [`dcm-anonymizer`](https://pypi.org/project/dcm-anonymizer/) engine.
- Stripe-backed subscription billing.
- Tamper-evident audit log (sha256 chain) per request.
- Per-tenant API key auth (Enterprise add optional OIDC).
- `/metrics` Prometheus endpoint (Pro and Enterprise).
- All updates within the same major version.

## What is NOT included

- Production patient consent flows. The Service pseudonymizes uploaded DICOM; lawful basis for the original processing is the Customer's responsibility.
- A guarantee that the pseudonymized output is anonymous data under GDPR. The output is pseudonymous personal data per WP29 Opinion 05/2014 and EDPB Guidelines 01/2025 on Pseudonymisation.
- A conformity assessment under EU MDR 2017/745 or AI Act 2024/1689. The Service is not a medical device.
- Image segmentation, AI inference, or clinical interpretation.

## Payment

- **Currency:** EUR.
- **Primary instrument:** Stripe Checkout — credit card, SEPA Direct Debit, and Apple/Google Pay where supported. Pro and Annual tiers via subscription; Enterprise via custom contract.
- **Bridge instruments (pre-Stripe live keys):** EU customers may also pay by SEPA bank transfer against a manual invoice issued from `legal/invoice-template.md`. Non-EU customers may pay by Wise transfer (EUR or USD). Contact `plusultra.dev@proton.me` to request a quote.
- **Billing cycle:** monthly in advance for Pro; annual in advance for Annual; net-15 invoice for Enterprise.
- **VAT:** B2B reverse-charge under Art. 196 Dir. 2006/112/EC for EU customers outside Spain (VATIN required on invoice). Out-of-scope for non-EU customers. Spanish-resident B2B customers and B2C customers in the EU are temporarily unsupported pending operator autónomo registration; contact for a custom quote in the interim.

## Refund policy

- Pro / Annual: pro-rated refund within 14 days of first payment for unused capacity, no questions. Subsequent months / years are non-refundable but cancellable for the next cycle through the Stripe customer portal.
- Enterprise: cancellation refund pro-rated to unused months minus a 10 % administrative fee, capped at one month equivalent.

## Tier change and cancellation

- **Upgrade:** Free → Pro / Annual takes effect immediately via Stripe Checkout. Pro → Annual is pro-rated at the next renewal.
- **Downgrade:** takes effect at the end of the current billing cycle. Paid customers receive an email before the renewal date.
- **Cancellation:** self-service via the Stripe customer portal once the `/v1/billing/portal-session` endpoint is enabled, otherwise email `plusultra.dev@proton.me` for cancellation in any cycle.

## How to start

- **Free tier:** Email `plusultra.dev@proton.me` from the same address you want to receive your API key on. Trial key issued within 24 hours; faster during European business hours.
- **Pro / Annual:** Call `POST /v1/billing/checkout-session` (see README §5) with your email. The Stripe Checkout link returned activates a 14-day free trial; the API key is issued automatically on first successful charge.
- **Enterprise:** Email `plusultra.dev@proton.me` with the request "Enterprise pricing" and a one-line description of the target deployment. First response within one Spanish business day.
