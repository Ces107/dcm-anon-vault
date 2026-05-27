# Kill-gate — dcm-anon-vault

**As-of:** 2026-05-20.

This document lists the explicit criteria under which the operator archives or pivots the venture. Per `CLAUDE.md` §9 and `skills/founder-agent-per-venture/SKILL.md`. No fudging on these dates: when the date arrives, the metric is what it is.

## Public launch reference date

The reference D-day is the first day Stripe live keys are wired and a public Show-HN-equivalent post happens under the operator identity. Currently TBD pending principal Stripe setup (ETA 2026-05-21).

Until D-day, the venture is in "internal scaffolding" state and kill-gates do not apply.

## D+14

**Hard archive triggers (any of):**

- < 5 ★ on the public GitHub repo, AND
- 0 distinct commercial-intent signals (paid trial activations, demo-request emails, sales calls scheduled).

**Hard "in danger" triggers (any of):**

- 0 free-tier trial activations beyond operator-self.
- 0 inbound emails of any kind beyond hello / typo reports.

## D+30

**Hard archive triggers (any of):**

- < 10 ★, AND 0 paid customers, AND 0 active commercial-intent conversations.
- < 25 free-tier trial activations.
- Stripe net revenue < €50 (i.e. less than 1 customer-month of Starter).

**Hard "in danger" triggers:**

- 1 paid customer and no second within sight.
- < 200 free-tier API requests served (i.e. the trials never actually use it).

## D+60

**Hard archive triggers (any of):**

- < 3 paid customers active.
- < €300 / month Stripe net revenue.
- > 1 documented complaint about correctness of pseudonymization output (NOT counted: feature requests).

## D+120

**Hard archive triggers (any of):**

- < €1,000 / month Stripe net revenue across all tiers.
- Net negative review momentum (more uninstalls / cancellations than activations 2 consecutive weeks).

## Non-kill considerations

The following ARE NOT kill triggers, even though tempting:

- Negative HN comments. (Signal != value. Hostility can correlate with attention.)
- Slow first month. (Healthcare buyer cycles are 60-90 days minimum.)
- Initial Stripe TOS friction. (One iteration is normal.)
- A competitor launching. (Validates market.)

## Capital cap

Venture-specific spend cap: €300 cumulative across infra (hosting, domain, Stripe fees beyond merchant fee, certificate costs). If the cap would be breached before D+60, escalate to principal as §12 review item; do not auto-extend.

## Auto-kill on §5 audit fail

Per `CLAUDE.md` §5: 2 substance-audit fails within 7 days → operator archives the venture. Substance fails include: claimed feature missing in code, claimed test missing, claimed customer fabricated.

## Archive procedure

When kill-gate triggers:

1. Stop accepting new paid trials (existing customers continue to end of cycle).
2. Move `workspaces/dcm-anon-vault/` to `archive/dcm-anon-vault-<date>/`.
3. Update `state/portfolio_ventures.yaml` status → `archived`.
4. Append entry to `LEDGER.md` with reason + metrics at archive.
5. Write a 1-page postmortem to `archive/dcm-anon-vault-<date>/postmortem.md` covering: what we built, what we expected, what happened, what we learned, which signals would have changed the outcome.
6. Open a follow-up ticket: which reusable parts (audit chain, tenant rate limiting, OIDC stubs) go back into the harness for future ventures.

## Re-baseline rule

If the venture survives all gates above and crosses €5,000 / month Stripe net revenue, re-baseline this kill-gate document with stricter criteria (lift to €15K then €30K thresholds). Do not allow indefinite "alive but mediocre" state.
