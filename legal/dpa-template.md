# Data Processing Agreement — dcm-anon-vault

**Template version:** 2026-05-27. Anchored on Article 28 GDPR and the EU Commission's Standard Contractual Clauses for controller-to-processor processing (Commission Decision 2021/915 of 4 June 2021).

This Data Processing Agreement ("DPA") supplements the dcm-anon-vault Terms of Service (`legal/tos.md`). It is executable on Customer request before any production processing of personal data and forms part of the agreement between the Customer and the Provider. In case of conflict, the order of precedence is: signed Order Form > this DPA > Terms of Service > Privacy Policy.

---

## Parties

**Controller (the "Customer"):**

- Legal name: [Customer legal name]
- Registered address: [address]
- Tax identifier: [VATIN or equivalent]
- Authorised signatory: [name, role]
- DPO or representative: [name, email] (or "Not appointed" with rationale)

**Processor (the "Provider"):**

- Legal name: César Pereiro García (autónomo / individual professional, trading as plusultra-tools)
- Registered address: [SPANISH ADDRESS]
- Tax identifier: NIF [TO PROVIDE]
- Contact for data protection matters: plusultra.dev@proton.me
- DPO: not appointed (processing does not meet Article 37 GDPR thresholds for mandatory DPO designation; the Provider will reassess if Customer volume crosses 50 active tenants or if a Customer contract requires it).

---

## 1. Subject matter and duration

1.1 The Provider processes personal data on behalf of the Customer solely to deliver the dcm-anon-vault hosted DICOM pseudonymization service ("the Service") as defined in the Terms of Service and the Customer's chosen tier (`pricing.md`).

1.2 The DPA enters into force on the date of signature of the last Party (or on first successful API call with a valid API key against a tenant where this DPA is on file, whichever is earlier) and remains in force for as long as the Provider processes personal data on the Customer's behalf, including any post-termination wind-down.

## 2. Nature and purpose of processing

2.1 **Nature:** Reception, transient in-memory pseudonymization, persistence of a tamper-evident audit log entry, and return of pseudonymized output to the Customer over an authenticated HTTPS channel.

2.2 **Purpose:** Enable the Customer to obtain DICOM PS3.15 Basic Confidentiality Profile pseudonymization as a hosted service, with audit traceability, for the Customer's documented purposes (typically scientific research, software development, or research-grade clinical pipelines).

2.3 **Types of personal data:** As contained in DICOM headers and bodies uploaded by the Customer. Typical categories include Patient Name, Patient ID, Patient Birth Date, Patient Sex, Referring Physician, Study Date/Time, Institution Name, and any other tags present per DICOM PS3.15. The Service does not decode burned-in pixel text; the Customer is responsible for pre-removing burned-in PHI or rejecting files where `BurnedInAnnotation==YES` (which the Service does automatically with HTTP 422).

2.4 **Categories of data subjects:** Patients whose DICOM studies are submitted by the Customer, and where applicable, healthcare professionals named in DICOM headers (referring physician, performing technologist).

2.5 **Special categories:** DICOM headers commonly contain data concerning health within the meaning of Article 4(15) GDPR. The Customer warrants that an Article 9 GDPR lawful basis exists for the original processing (typically Art. 9(2)(j) for scientific research with applicable Member State law, or another Art. 9 derogation).

## 3. Documented instructions

3.1 The Provider processes personal data only on the Customer's documented instructions, including with regard to transfers, except where Union or Member State law requires otherwise (Art. 28(3)(a) GDPR). The instructions are: (i) these DPA terms; (ii) the Terms of Service; (iii) the Customer's API calls as authenticated by valid credentials; (iv) any further written instructions agreed by both Parties.

3.2 The Provider shall immediately inform the Customer if, in its opinion, an instruction infringes GDPR or other applicable Union or Member State data protection law.

3.3 Any processing outside these documented instructions requires the Customer's prior written consent.

## 4. Confidentiality

The Provider ensures that persons authorised to process personal data under this DPA have committed themselves to confidentiality or are under an appropriate statutory obligation of confidentiality (Art. 28(3)(b) GDPR). Currently the Provider is a sole-operator entity; no additional personnel handle personal data.

## 5. Security of processing

5.1 The Provider implements appropriate technical and organisational measures (TOMs) per Article 32 GDPR. The current TOMs are documented in `docs/security.md` and include, at minimum:

- TLS 1.2 or higher for all data in transit.
- Encryption at rest of object storage and database (deployment-specific; default Fly.io volumes are encrypted).
- API keys stored as salted SHA-256 hashes; raw values visible only at issuance.
- Tamper-evident SHA-256 audit chain.
- Per-tenant API-key isolation, rate limiting, and webhook signature verification.
- Optional OIDC integration for federated identity.
- Backup encryption with keys held in a separate key store.
- Vulnerability disclosure programme per `SECURITY.md` with 72-hour acknowledgement and 30-day fix SLA.

5.2 The Provider may update TOMs without prior notice provided the security level is not materially decreased.

## 6. Sub-processors

6.1 The Customer grants the Provider general authorisation to engage sub-processors under Article 28(2) GDPR. The current sub-processor list, kept current in `docs/subprocessors.md` (if and when applicable), includes:

- Stripe Payments Europe Limited (Ireland) — payment processing.
- Fly.io Inc. (USA) — hosting (default deployment region: `cdg` Paris, EU).
- The Customer's chosen hosting provider where the Customer self-deploys.
- Backup / object storage provider as documented in `docs/deploy.md`.

6.2 The Provider shall notify the Customer of any intended addition or replacement of sub-processors with at least 30 days notice by email to the tenant administrative contact. The Customer may object on reasonable data-protection grounds; if the Parties cannot agree on a remediation within 30 days of objection, the Customer may terminate the affected services with pro-rated refund of prepaid unused fees.

6.3 The Provider shall impose on each sub-processor data protection obligations no less protective than this DPA, in writing.

## 7. International transfers

7.1 The Provider may transfer personal data outside the European Economic Area only on the basis of:

(a) an adequacy decision under Article 45 GDPR;
(b) Standard Contractual Clauses approved by the European Commission under Article 46(2)(c) GDPR (Commission Implementing Decision 2021/914 of 4 June 2021), incorporated by reference; or
(c) any other valid mechanism under Article 46 GDPR.

7.2 The current default deployment region is `cdg` (Paris, EU). Hosting on Fly.io US regions or other non-EU regions is available on Customer request and triggers SCCs Module Two with the Provider as data exporter and the hosting sub-processor as data importer.

## 8. Assistance to the Customer

8.1 The Provider assists the Customer, by appropriate technical and organisational measures and taking into account the nature of the processing and the information available, to fulfil the Customer's obligations:

(a) To respond to data subject requests (Art. 12-23 GDPR). The Provider will forward any such request received about Customer-controlled data within 5 working days. The Provider does not decode DICOM pixel data; data subject requests requiring re-identification or content retrieval are the Customer's responsibility as controller.

(b) To ensure security of processing (Art. 32 GDPR), per `docs/security.md`.

(c) To notify and communicate personal data breaches (Art. 33-34 GDPR). The Provider notifies the Customer of any personal data breach affecting the Customer's data without undue delay and at the latest within 48 hours of becoming aware. The breach notification includes the categories and approximate number of data subjects and records concerned (to the extent known), the likely consequences, and measures taken or proposed to address the breach.

(d) To conduct data protection impact assessments (Art. 35 GDPR) and prior consultations (Art. 36 GDPR), to the extent reasonable taking into account the information available to the Provider.

8.2 Assistance under §8.1(c) and (d) beyond standard support volumes may be subject to reasonable additional charges agreed in writing.

## 9. Records of processing

9.1 The Provider maintains records of processing activities under Article 30(2) GDPR. The records are available to the Customer's competent supervisory authority on request.

9.2 The Provider makes available to the Customer all information necessary to demonstrate compliance with Article 28 GDPR. The Customer may audit (or appoint an independent third-party auditor under written confidentiality terms) on reasonable prior notice, no more than once per 12 months unless triggered by a specific incident, at the Customer's expense. The Provider may satisfy the audit obligation by providing a recent independent assessment (SOC 2, ISO 27001, ISAE 3000) where available.

## 10. Personal data breaches

10.1 The Provider notifies the Customer of a personal data breach within 48 hours of becoming aware.

10.2 The notification contains, to the extent known at the time:

(a) Nature of the breach including categories and approximate numbers of data subjects and records.
(b) Likely consequences.
(c) Measures taken or proposed to address the breach and mitigate adverse effects.
(d) Provider's contact point for further information.

10.3 The Provider does not notify the supervisory authority on the Customer's behalf; that obligation remains with the Customer as controller.

## 11. Deletion or return of personal data

11.1 At the choice of the Customer, the Provider deletes or returns all personal data to the Customer after the end of the provision of services, and deletes existing copies, unless Union or Member State law requires storage of the personal data.

11.2 Standard return mechanism: API export of audit log entries via the Customer's existing endpoint access, plus on request a one-time export bundle (ZIP) within 14 days. Standard deletion mechanism: physical deletion within 30 days of termination, save for backups which rotate out within 30 days of the deletion date.

11.3 The Provider provides written confirmation of deletion to the Customer on request.

## 12. Liability

12.1 Each party is liable for the damage it has caused by processing that infringes GDPR. The Provider's liability under this DPA is subject to the limitation set out in §9 of the Terms of Service.

12.2 Where both parties are responsible for damage to data subjects, joint and several liability under Article 82(4) GDPR applies, without prejudice to the limitations between the Parties in §12.1.

## 13. Term and termination

13.1 This DPA terminates automatically on termination of the Service Agreement.

13.2 Provisions of this DPA which by their nature should survive termination (§9, §11, §12) survive.

## 14. Modifications

The Provider may propose modifications to this DPA on 60 days written notice where required by changes in applicable law, regulatory guidance, or technical organisation. The Customer's continued use of the Service after the effective date of a non-detrimental amendment constitutes acceptance. The Customer may terminate the affected services with pro-rated refund if it does not accept a proposed amendment.

## 15. Order of precedence

In the event of inconsistency, the order of precedence is: signed Order Form > this DPA > Terms of Service > Privacy Policy.

## 16. Governing law and jurisdiction

Spanish law. Exclusive jurisdiction of Valencia, Spain courts. Either party may seek injunctive relief in the jurisdiction of the breach.

---

## Annex I — Description of the transfer (where Module Two SCCs are incorporated under §7)

**Data exporter:** [Customer legal name and address]
**Data importer (in non-EU sub-processor context):** [sub-processor name and country]

**Categories of data subjects:** patients of the Customer; healthcare professionals named in DICOM headers.

**Categories of personal data:** DICOM header personal data (Patient Name, Patient ID, Patient Birth Date, Patient Sex, Referring Physician, Study Date/Time, Institution Name, and tags listed in PS3.15 Basic Profile).

**Special categories:** data concerning health (Art. 4(15) GDPR).

**Frequency of transfer:** continuous (on each API call).

**Nature of processing:** pseudonymization per PS3.15 Basic Profile and audit logging.

**Purpose:** delivery of the dcm-anon-vault hosted service.

**Retention:** transient processing; audit log retention per tier (see `pricing.md` and `legal/privacy.md` §7).

## Annex II — Technical and organisational measures

Per `docs/security.md`. Summary:

- Encryption in transit (TLS 1.2+).
- Encryption at rest (deployment-default).
- Access control (per-tenant API keys, hashed at rest; optional OIDC).
- Tamper-evident SHA-256 audit chain.
- Backup encryption with separated key store.
- Vulnerability management per `SECURITY.md`.
- Logging and monitoring (`/metrics` endpoint, structured access logs).
- Incident response per §10 of this DPA.

## Annex III — Sub-processors

Current list maintained in `docs/subprocessors.md` and §6.1 of this DPA. Updated with 30-day notice per §6.2.

---

## Signatures

**For the Customer:**

Name: ________________________________________________
Title: _________________________________________________
Date: __________________________________________________
Signature: ____________________________________________

**For the Provider:**

Name: César Pereiro García
Title: Sole operator, plusultra-tools
Date: __________________________________________________
Signature: ____________________________________________

---

*Notice: this template is provided as a starting point. The Customer's legal counsel should review before execution. The Provider reserves the right to negotiate Customer redlines on a case-by-case basis. This template adopts the substance of EU Commission Decision 2021/915 of 4 June 2021 ("controller-to-processor SCCs"); for cross-border transfers, Commission Implementing Decision 2021/914 of 4 June 2021 ("transfer SCCs Module Two") is incorporated by reference under §7.*
