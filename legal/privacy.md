# Privacy Policy — dcm-anon-vault

**Last updated:** 2026-05-20.

This policy describes how plusultra-tools / César Pereiro García (the "Provider", "we") processes personal data in connection with the dcm-anon-vault hosted API ("the Service"). The policy is designed to comply with Regulation (EU) 2016/679 (GDPR) and Spanish Ley Orgánica 3/2018 (LOPDGDD).

## 1. Data controller

César Pereiro García, individual professional, [SPANISH ADDRESS], NIF [TO PROVIDE]. Contact: plusultra.dev@proton.me.

No DPO has been appointed because the processing does not meet the Article 37 GDPR thresholds for mandatory DPO designation. We will reassess this when customer volume crosses 50 active tenants, and on any contract requiring DPO designation by the Customer.

## 2. Roles

For DICOM data uploaded to the Service:

- The **Customer is the data controller** of the uploaded DICOM files and the underlying patient data.
- **We act as data processor** under Art. 28 GDPR, on the Customer's documented instructions, per a Data Processing Agreement (DPA) executable on Customer request.

For the Customer's own business contact data (account holder name, email, billing address) we act as data controller.

## 3. Categories of personal data processed

### 3.1 Customer contact data (we are controller)

(a) Account holder name and business email.
(b) Tenant primary contact (technical and billing).
(c) Billing address, VATIN, invoicing email.
(d) Payment metadata processed via Stripe (we never see full card numbers).
(e) Support correspondence.

### 3.2 DICOM file content (we are processor)

DICOM files uploaded for pseudonymization typically contain personal data of patients in tag headers (Patient Name, Patient ID, Birth Date, Referring Physician, etc.) and pixel data (where burned-in text is present). Our processing rewrites these tags per the PS3.15 Basic Confidentiality Profile and discards original mappings within the request lifecycle except where the Customer's tier explicitly retains them (Enterprise tier audit chain).

We do **not** decode pixel-data text. Customers requiring burned-in-text scrubbing should pre-process before upload or use the upcoming dicom-sr-scrubber companion product.

### 3.3 Audit log (we are processor)

Per-request log entries record: tenant id, request id, file count, file size totals, timestamps, success / error status, and a sha256 chain hash. Audit log entries do NOT contain personal data extracted from DICOM tags. Retention per tier (see `pricing.md`).

## 4. Legal bases

For Customer contact data:

- Performance of contract (Art. 6(1)(b) GDPR) for delivering the Service.
- Legal obligation (Art. 6(1)(c) GDPR) for accounting records (6 years per Spanish tax law).
- Legitimate interest (Art. 6(1)(f) GDPR) for product analytics on a tenant-aggregated, non-identifying basis.

For DICOM data (where we are processor):

- The Customer's documented lawful basis (typically Art. 9(2)(j) GDPR for scientific research, or another Art. 9 derogation), under DPA terms.

## 5. Recipients

We do not sell or rent personal data. Categories of recipients:

(a) **Stripe Payments Europe Limited** (Ireland): payment processor. Subject to Stripe's GDPR-compliant terms.
(b) **Hosting provider:** as documented in `docs/deploy.md` (currently the Provider's controlled infrastructure or the Customer's chosen deployment target, depending on tier).
(c) **Backup / object storage provider:** as documented in `docs/deploy.md` and the DPA, encrypted at rest.
(d) **Spanish tax authority (AEAT):** for invoicing and tax records when legally required.
(e) **Professional advisors** (accountant, lawyer) on a need-to-know basis under confidentiality.

No marketing-driven third-party sharing. No automated decision-making producing legal effects (Art. 22 GDPR not applicable).

## 6. International transfers

Any transfers outside the EEA are covered by adequacy decisions, Standard Contractual Clauses approved by the European Commission, or other valid Art. 46 GDPR mechanisms. Specifics are documented in the DPA.

## 7. Retention

- **Customer contact / billing data:** duration of the relationship plus 6 years for tax compliance, then deleted.
- **DICOM file content:** request-lifetime only; deleted after pseudonymization and delivery, except for the Enterprise tier audit chain artefacts retained per the tier specification (default 6 years; configurable down to 30 days).
- **Audit log entries:** retention per tier (30 days Starter, 1 year Team, 6 years Enterprise; configurable Enterprise).
- **Backups:** rolling 30 day window, encrypted.
- **Marketing contact data (where explicit consent obtained):** retained until consent withdrawal or 3 years of inactivity.

## 8. Data subject rights

Where we are controller, data subjects have the rights under GDPR Art. 15-22:

(a) Access.
(b) Rectification.
(c) Erasure (subject to legal-retention exceptions).
(d) Restriction.
(e) Portability.
(f) Objection.
(g) Withdraw consent.
(h) Lodge a complaint with the Spanish supervisory authority (AEPD).

For DICOM-data data subjects, requests should be directed to the Customer (the data controller for that processing). We will assist Customers in fulfilling their obligations per Art. 28(3)(e) GDPR.

To exercise rights against us as controller: email plusultra.dev@proton.me with subject "GDPR request". We respond within 30 days as required by Art. 12(3) GDPR.

## 9. Security

- All Service traffic uses TLS 1.2+ in transit.
- Object storage and database storage are encrypted at rest.
- API keys are stored as salted hashes; the raw key value is visible only at issuance.
- Audit log is tamper-evident (sha256 chain).
- Per-tenant rate limiting and webhook signature verification mitigate abuse.
- Optional OIDC integration for Customers requiring federated identity.
- Backup encryption keys are held in a separate key store.

Full security model and threat model: `docs/security.md`.

## 10. DICOM-specific considerations

The Service processes DICOM PS3.10 files using the PS3.15 Basic Confidentiality Profile plus additional configurable tag handling. **Output is pseudonymous personal data, not anonymous data**, per WP29 Opinion 05/2014 and EDPB Guidelines 01/2025. Customers MUST treat output as personal data for compliance purposes unless an independent assessment establishes anonymity in the specific dataset and downstream use context.

## 11. Children

The Service is B2B. Patient data of minors may be processed only on the Customer's lawful basis under its DPA with us; we do not knowingly process minors' data outside that scope.

## 12. Changes

We may update this policy. Material changes will be communicated via email to active tenant contacts with 30 days notice. The "last updated" date at the top of this document is canonical.

## 13. Contact

- **Privacy queries:** plusultra.dev@proton.me (subject "GDPR request" or "Privacy").
- **Spanish supervisory authority:** Agencia Española de Protección de Datos (AEPD), C/ Jorge Juan 6, 28001 Madrid, Spain. https://www.aepd.es.
