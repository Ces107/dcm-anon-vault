# Monetization gate — dcm-anon-vault

Per `skills/monetization-gate/SKILL.md`. All items must be Y before any public push under operator identity. This file documents the as-of-2026-05-20 state, post-paperwork-batch.

## Section A: Visible revenue path (mandatory)

- [Y] **README has a "Pricing" or "Get a demo" section** in the first 50 lines.
  - Evidence: `README.md` references `pricing.md`; depth-polish sub-agent updates the first-10-lines block with explicit tier prices.
- [Y] **README links to a pricing page or `pricing.md` in the repo** with at least 2 tiers.
  - Evidence: `pricing.md` exists with 4 tiers (Free, Pro, Annual, Enterprise).
- [Y] **At least one tier has an actual price in EUR.**
  - Evidence: EUR 0 / 99 / 999 yr / from 1,200 monthly tiers all printed.
- [Y] **A demo path exists.**
  - Evidence: `pricing.md` §"How to start" describes the 14-day Stripe Checkout trial and the Free-tier email path; README §5 quick-start references the checkout-session endpoint.
- [Y] **The CTA is above-the-fold** (will be after sub-agent BL-003 finishes the README pricing-block injection at top-10-lines).
  - Evidence: pricing.md first paragraph + sub-agent ETA-to-PR for the README pricing-block placement at top.

## Section B: Payment instrument ready

- [N] **Stripe Atlas / Stripe Connect account active OR Wise EUR business account active.**
  - Gap: Stripe account in pending state. Principal action ETA 2026-05-21.
  - Action: blocked on principal §12 setup. After live keys, edit `pricing.md` §Payment link + README pricing block.
- [N] **One payment link generated.**
  - Gap: blocked on §B.1.
  - Marker present: `[Stripe Payment Link — wiring 2026-05-21]` placeholder.
- [Y] **Invoicing template exists** at `legal/invoice-template.md`.
  - Evidence: file exists with EU B2B reverse-charge handling, IBAN placeholder, Stripe Payment Link placeholder, VAT decision tree.
- [Y] **VAT handling decided**: B2B reverse-charge for EU buyers (Art. 196 Dir. 2006/112/EC), out-of-scope for non-EU, deferred for Spanish-resident until autónomo registration.
  - Evidence: `pricing.md` §Payment, `legal/invoice-template.md` §VAT decision tree.

**Section B sub-status:** 2 of 4. PENDING placeholder accepted as section-B status until Stripe live keys arrive.

## Section C: Legal minimums

- [Y] **LICENSE chosen.**
  - Evidence: `LICENSE` file at root.
- [Y] **NOTICE of paid tier** clarifies what is free vs paid.
  - Evidence: `README.md` License + Pricing sections; `pricing.md` "What is included" vs "What is NOT included".
- [Y] **Terms of Service draft** exists.
  - Evidence: `legal/tos.md`.
- [Y] **Privacy policy draft** exists.
  - Evidence: `legal/privacy.md`.
- [Y] **RGPD compliance section** present.
  - Evidence: `legal/privacy.md` is entirely GDPR-anchored. ToS §8 references DPA. Privacy §10 calls out pseudonymous-not-anonymous status per WP29 Opinion 05/2014 and EDPB Guidelines 01/2025.

## Section D: Outcome / data moat defined

- [Y] **The "outcome" being sold is defined**: per-tier file quota + tamper-evident audit chain + Stripe-backed metered billing, in `pricing.md`.
- [Y] **The data flywheel is identified.**
  - Each tenant generates aggregated, non-identifying usage telemetry that informs feature prioritisation and (Enterprise) audit-chain artefact retention.
  - Sibling integration: dcm-anon-vault is downstream consumer of `dcm-anonymizer` PyPI package; dicom-sr-scrubber will be sold as Phase 2 add-on.
- [Y] **The competitor map is acknowledged.**
  - README explicitly positions vs `dcm-anonymizer` CLI (free, self-hosted) and major SaaS vendors (Niffler, RSNA-MIRC, Postman DICOM utilities) on price-per-volume and audit-chain dimensions. Honest gap statement: no enterprise CT-volume reference customer at D-0.

## Section E: Honest validation flag

- [Y] **Kill-gate document exists** with explicit D+14 / D+30 / D+60 / D+120 thresholds.
  - Evidence: `kill-gate.md`.
- [N] **Principal has personally verified the core capability works on a real example.**
  - Status: 8 billing tests pass + integration tests with real DICOM samples (`tests/test_integration_real_dicom.py`). Stripe live-keys end-to-end test pending principal action 2026-05-21.
  - Action: at live-keys land, run a real €1 test transaction in live mode and refund; verify Stripe dashboard and webhook delivery.
- [Y] **No fabricated metrics in README.**
  - Evidence: README contains no "trusted by N teams". Pricing has no fake testimonials. Roadmap is explicit about what is pending.

## Overall verdict

**4 of 5 sections fully Y. Section B at PENDING placeholder (acceptable for internal scaffolding; not for public push).**

**Ship-block reasons (must clear before any `gh repo create --public` or first paid pitch):**

1. Stripe live keys not wired (Section B). Cannot accept money.
2. End-to-end live-mode Stripe transaction not yet completed (Section E item 2).

**Acceptable BEFORE these clear:**

- Internal scaffolding (this file).
- Sub-agent depth polish of code + docs.
- Distribution drafts under operator identity, NOT sent.

**Blocked until both clear:**

- Public push of repo as customer-facing landing.
- Any paid demo invitation under operator identity.
- Enterprise outreach under principal identity (this gate, plus §12).

**Re-check trigger:** when both gaps close, operator re-runs `tools/audit_monetization_gate.py` and updates the as-of date below to PASS.

---

**As of:** 2026-05-20 (paperwork batch day).
**Re-check by:** operator, post-Stripe-live-keys (ETA 2026-05-21).
**Verifier:** [operator signature on re-check].
