# dcm-anon-vault vs the alternatives

Last updated: 2026-05-20. This document is honest. If you find a misrepresentation, open an issue.

## Why this exists

You can pseudonymize DICOM files in many ways. This doc explains where dcm-anon-vault sits on a few axes that buyers care about, and where the alternatives win.

## Axes that matter

1. **Deployment model**: do you run the engine yourself or do you call a hosted API?
2. **Audit trail**: is what was changed, by whom, when, retrievable months later?
3. **Tenant isolation**: can two customers share one deployment safely?
4. **Compliance posture**: does it admit honestly that output is pseudonymous (not anonymous) under GDPR?
5. **Billing**: pay-as-you-go, subscription, or perpetual license?
6. **EU regulatory anchoring**: does it cite EU sources or is everything HIPAA-anchored from the US?

## Alternatives

### Niffler (Emory University)

[github.com/Emory-HITI/Niffler](https://github.com/Emory-HITI/Niffler). Pipeline tool for de-identifying DICOM at scale in research settings.

| Axis | Niffler | dcm-anon-vault |
|------|---------|----------------|
| Deployment | Self-host | Hosted API or self-host |
| Audit trail | Custom; per-deployment | Tamper-evident sha256 chain, default-on |
| Tenant isolation | Single-tenant per deployment | Multi-tenant with per-API-key isolation (Team / Enterprise) |
| Compliance posture | "De-identification"; HIPAA framing | "Pseudonymization"; WP29 Op. 05/2014 + EDPB 01/2025 framing |
| Billing | Free OSS | Tiered subscription + overage |
| EU anchoring | Light | Primary |

**When Niffler wins:** large research consortia with in-house DevOps, comfortable building the rest of the stack. Free.

**When dcm-anon-vault wins:** EU SaaS / scale-up that does not want to operate the pipeline. Multi-tenant billing baked in. Audit trail mandatory.

### RSNA MIRC CTP DICOM Anonymizer

[mircwiki.rsna.org/index.php?title=DICOM_Anonymizer](https://mircwiki.rsna.org/index.php?title=DICOM_Anonymizer). Java tool, part of the broader Clinical Trial Processor stack. Highly configurable rule engine. Mature.

| Axis | MIRC CTP | dcm-anon-vault |
|------|----------|----------------|
| Deployment | Self-host (Java app, on-prem) | Hosted API or self-host (container) |
| Audit trail | XML logs | Hash-chained log |
| Tenant isolation | Per-deployment | Multi-tenant |
| Compliance posture | Clinical-trial framing | EU SaaS framing |
| Billing | Free OSS | Subscription |
| EU anchoring | Light | Primary |
| Configurability | Very high (full rule DSL) | Moderate (PS3.15 profile + add-on rules) |

**When MIRC CTP wins:** complex clinical-trial sites with bespoke rules for each sponsor; you have an IT team that knows Java and likes XML.

**When dcm-anon-vault wins:** you want PS3.15 Basic Confidentiality out of the box + an HTTP API + Stripe billing on day 0 + a self-explanatory audit chain that auditors will accept.

### `dcm-anonymizer` (upstream CLI by the same author)

[pypi.org/project/dcm-anonymizer](https://pypi.org/project/dcm-anonymizer). The CLI we build on. MIT.

| Axis | dcm-anonymizer | dcm-anon-vault |
|------|----------------|----------------|
| Deployment | CLI on the user's machine | Hosted API |
| Audit trail | None | Hash-chained log |
| Tenant isolation | N/A | Multi-tenant |
| Compliance posture | Same | Same |
| Billing | Free (MIT) | Subscription |

**When dcm-anonymizer wins:** developer prototyping. Single user. Local data. Free.

**When dcm-anon-vault wins:** customers do not run the CLI; they want an HTTP endpoint, billing, and audit. Same engine, packaged for buyers, not for engineers.

### gdcm-anonymize

[gdcm.sourceforge.net](http://gdcm.sourceforge.net). C++ DICOM library tooling. Low level.

| Axis | gdcm-anonymize | dcm-anon-vault |
|------|----------------|----------------|
| Deployment | C++ library / CLI | Hosted API |
| Audit trail | None | Hash-chained log |
| Billing | Free | Subscription |
| API ergonomics | Low (C++) | High (REST) |

**When gdcm wins:** you are embedding DICOM handling into a desktop or medical-imaging product written in C++.

**When dcm-anon-vault wins:** the alternative is wrapping gdcm yourself and building all the SaaS plumbing.

### Commercial: GE Healthcare, Philips, Siemens internal tools

Bundled with hospital PACS deployments. Not separately licensable. Configuration varies.

| Axis | Vendor PACS | dcm-anon-vault |
|------|-------------|----------------|
| Deployment | Bundled with PACS | Independent of PACS |
| Cost | Part of PACS license | Separate subscription |
| Multi-vendor | Tied to one vendor | Vendor-agnostic |

**When vendor PACS wins:** your hospital has standardized on one PACS vendor and uses their de-identification module for internal workflows.

**When dcm-anon-vault wins:** you build software that runs against many hospitals' PACS, OR you build a research pipeline that ingests DICOM from heterogeneous sources, OR you want a vendor-agnostic public-API workflow.

### TCIA Posda (NCI Imaging Data Commons tooling)

[github.com/CBIIT/NBIA-TCIA](https://github.com/CBIIT/NBIA-TCIA). The pipeline NCI uses to de-identify DICOM for the TCIA public archive.

Heavy, specific to NCI's workflow. Excellent for the TCIA use case; not a drop-in for a SaaS.

**When Posda wins:** you are mirroring TCIA's workflow at the same scale.

**When dcm-anon-vault wins:** anything else.

## Where dcm-anon-vault explicitly does NOT win

Things we are not pretending to be:

- **A full clinical-trial pseudonymization platform with sponsor-specific rule DSL.** Use MIRC CTP.
- **An on-prem-only solution for a hospital that mistrusts hosted services.** Self-host is supported, but the docker-compose + observability story is most polished for hosted.
- **A free OSS tool you can use forever without paying anyone.** The free trial tier and the upstream `dcm-anonymizer` CLI cover the OSS path. The hosted product is paid.
- **A CE-marked medical device.** It is not a medical device.
- **A SOC 2 / ISO 27001 certified service.** At D-0 we do not carry these certifications. Roadmap item for D+180 if revenue justifies.
- **A magic anonymization step that makes patient data legally anonymous under GDPR.** Output is pseudonymous personal data, and the docs say so.

## How to choose

Decision tree:

1. Do you need an HTTP API that returns pseudonymized DICOM and a hash-chained audit log? **Yes →** dcm-anon-vault is the simplest fit. **No →** consider the CLI alternatives.
2. Do you need very complex rules (multiple study types, multiple sponsors, custom mapping per project)? **Yes →** MIRC CTP. **No →** dcm-anon-vault.
3. Do you need multi-tenant isolation with per-tenant billing? **Yes →** dcm-anon-vault (Team or Enterprise tier). **No →** any of the free CLIs.
4. Are you EU and need an EU-anchored data-protection posture documented? **Yes →** dcm-anon-vault. **No →** US-anchored tools are fine.
5. Are you cost-sensitive and have engineering time? **Yes →** build on the free CLIs. **No →** dcm-anon-vault.

If you are unsure, the trial tier (100 files / month) lets you exercise the API for two weeks before committing.

## Honest gaps we will close

- **Drop-in import from MIRC CTP rule files.** Roadmap, D+90.
- **Per-customer custom rule DSL (beyond PS3.15 profile add-ons).** Roadmap, D+180 if Enterprise demand justifies.
- **OIDC SAML interop tested against Keycloak, Okta, Azure AD.** Stubs ship in 0.2; real integration tests roll in by D+60.
- **SOC 2 readiness assessment.** Not started. Wait for revenue.

## Source for this doc

- Niffler README, accessed 2026-05-20.
- MIRC CTP wiki, accessed 2026-05-20.
- gdcm SourceForge, accessed 2026-05-20.
- NCI Posda repo, accessed 2026-05-20.
- Author's prior employment at Laberit (HIS/RIS/PACS-adjacent) for general PACS-vendor framing only. No Laberit-confidential information is used in this doc.
