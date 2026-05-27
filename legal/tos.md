# Terms of Service — dcm-anon-vault

**Effective:** 2026-05-20.

These Terms govern use of the dcm-anon-vault hosted API ("the Service") operated by plusultra-tools / César Pereiro García ("the Provider") on behalf of the customer ("the Customer"). They are accepted by clicking "I agree" at signup, or implicitly on first API call with a valid API key, whichever is earlier.

## 1. Service description

The Service is a REST API that, given DICOM files uploaded by the Customer, applies the DICOM PS3.15 Basic Confidentiality Profile (and configurable additional tag handling) and returns pseudonymized DICOM files plus a tamper-evident audit log. Tier limits and what is included are defined in `pricing.md`.

## 2. Account and credentials

(a) The Customer is responsible for the confidentiality of API keys and OIDC client secrets issued to the Customer's tenant.
(b) Any action authenticated by a valid Customer credential is deemed taken by the Customer for billing and audit purposes.
(c) The Provider may revoke credentials on suspected abuse, with prompt notice to the Customer.

## 3. Fees, billing, taxes

- Fees per `pricing.md`, in EUR net of VAT.
- Stripe processes payments; the Provider never stores full card data.
- Overage billed monthly at the rate stated in `pricing.md` §Tiers.
- VAT treatment per `pricing.md` §Payment.
- Late payment accrues statutory commercial interest per Spanish Ley 3/2004 and Directive 2011/7/EU. Continued non-payment beyond 30 days entitles the Provider to suspend Service.

## 4. Acceptable use

The Customer shall not:

(a) Upload data the Customer is not lawfully entitled to process.
(b) Use the Service to attempt to RE-identify pseudonymized records produced by the Service.
(c) Run penetration tests, security scans, or DoS-class load tests against the Service without prior written consent from the Provider.
(d) Resell access to the API as a substitute service without a separate written agreement.
(e) Attempt to extract, copy, or reverse-engineer the Provider's pseudonymization mappings, audit chain, or model internals.

Violations may trigger suspension and termination.

## 5. Provider commitments

The Provider shall:

(a) Apply DICOM PS3.15 Basic Confidentiality Profile transformations as documented in `docs/security.md`.
(b) Maintain a tamper-evident hash chain on the audit log per `docs/security.md`.
(c) Issue invoices and receipts via Stripe.
(d) Notify the Customer of material Service changes 30 days in advance via email to the registered tenant contact.
(e) Apply commercially reasonable security measures per `docs/security.md`.

## 6. What the Service is NOT

(a) **Not a medical device.** Output is not for primary diagnostic use. Pseudonymization is engineering processing, not clinical interpretation.
(b) **Not a guarantee of anonymity.** Output is pseudonymous personal data per WP29 Opinion 05/2014 and EDPB Guidelines 01/2025 on pseudonymization. The Customer remains data controller for re-identification risk in downstream use.
(c) **Not legal advice.** Compliance with GDPR, EU MDR, AI Act, or other regulation is the Customer's responsibility.
(d) **Not a conformity assessment.** No CE marking, FDA clearance, or notified-body opinion is implied.
(e) **Not an insurance policy.** Regulatory and contractual risk remains with the Customer.

## 7. Intellectual property

(a) Customer-uploaded DICOM data and metadata remain owned by the Customer (or its data subjects, as applicable). The Provider's processing rights are limited to those necessary to deliver the Service.
(b) The Provider owns the Service code (including audit chain, billing logic, OIDC integration), its pseudonymization mapping schema, and any aggregated/anonymized usage metrics.
(c) The Provider grants the Customer a non-exclusive, non-transferable, worldwide license to use the Service per these Terms during the subscription period.

## 8. Data protection

Per the Privacy Policy (`legal/privacy.md`) and the Data Processing Agreement template at `legal/dpa-template.md` (executable on Customer request before processing personal data). For GxP and hospital deployments a written DPA is mandatory before production traffic.

## 9. Limitation of liability

To the maximum extent permitted by law:

(a) The Provider's total aggregate liability for any claim under these Terms is capped at the total fees paid by the Customer in the 12 months preceding the event giving rise to the claim, or EUR 1,000, whichever is greater.
(b) Neither party is liable for indirect, consequential, incidental, special, or punitive damages.
(c) The cap does not apply to liability that cannot be limited under mandatory law (gross negligence, wilful misconduct, death / personal injury caused by negligence, fraud).

## 10. Indemnification

Each party indemnifies the other against third-party claims arising from its own material breach of these Terms or its negligent or wilful misconduct, subject to §9.

## 11. Confidentiality

Each party shall protect the other party's non-public information with the same care it uses for its own non-public information of similar sensitivity (no less than reasonable care). The Provider shall not use Customer data for any purpose other than delivering the Service, except to compute aggregated, non-identifying usage statistics.

## 12. Force majeure

Neither party is liable for failure to perform caused by events beyond reasonable control (natural disaster, war, large-scale internet infrastructure outage, government action). The affected party gives prompt notice and resumes performance as soon as practicable.

## 13. Termination

(a) For convenience: either party may terminate at the end of the current billing cycle by written notice.
(b) For cause: either party may terminate immediately on material breach not cured within 14 days of written notice.
(c) On termination, the Provider deletes Customer data per the retention policy in `pricing.md` §Tiers and `legal/privacy.md` §Retention.
(d) Surviving clauses: §6, §7, §9, §10, §11 (for 3 years), §15.

## 14. Modifications

The Provider may update these Terms by giving 30 days written notice to the Customer at the registered tenant contact email. Continued use after the effective date constitutes acceptance.

## 15. Governing law and jurisdiction

Spanish law. Exclusive jurisdiction of Valencia, Spain courts. Either party may seek injunctive relief in the jurisdiction of the breach.

## 16. Severability

If any provision is held unenforceable, the remainder remains in force.

## 17. Notices

Notices must be in writing. The Provider's notice address: plusultra.dev@proton.me. The Customer's notice address is the email associated with the tenant.

## 18. Entire agreement

These Terms plus the Privacy Policy, applicable Data Processing Agreement, and Order Form (Stripe checkout receipt or signed enterprise order) constitute the entire agreement. In case of conflict: signed Order Form > DPA > these Terms > Privacy Policy.
