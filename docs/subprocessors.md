# Sub-processors — dcm-anon-vault

**Last updated:** 2026-05-27.

This page lists the sub-processors engaged to deliver the dcm-anon-vault
hosted service, per Article 28(2) GDPR and §6 of the
[Data Processing Agreement](../legal/dpa-template.md). The Provider notifies
Customers of any intended addition or replacement with at least 30 days
notice (DPA §6.2).

For self-hosted deployments, the Customer chooses its own hosting and
storage providers; only Stripe (billing) applies in that case, and only
if the Customer enables the billing endpoints.

| Sub-processor | Purpose | Location | Data categories | Safeguard |
|---------------|---------|----------|-----------------|-----------|
| Stripe Payments Europe Ltd. | Subscription billing, payment processing | Ireland (EU) | Customer business contact + payment metadata (never full card data) | EU-domiciled; Stripe GDPR DPA |
| Fly.io Inc. | Hosting (default deployment) | Default region `cdg` (Paris, EU); other regions on Customer request | DICOM in transient processing + audit log at rest | EU region default; SCCs Module Two if a non-EU region is selected (DPA §7) |
| (Customer-selected hosting) | Hosting (self-host path) | Customer's choice | As above | Customer-controlled; outside the Provider's sub-processor scope |

## Notes

- The default Fly.io deployment region is `cdg` (Paris, EU). Selecting a
  non-EU Fly.io region triggers Standard Contractual Clauses Module Two
  with the Provider as data exporter (DPA §7).
- No analytics, advertising, or marketing-driven third-party sharing is
  performed (privacy.md §5).
- Backup / object storage, where used, is documented in
  [`deploy.md`](./deploy.md) and encrypted at rest.

To object to a sub-processor on reasonable data-protection grounds, email
`plusultra.dev@proton.me` with the subject "Sub-processor objection". See
DPA §6.2 for the remediation process.
