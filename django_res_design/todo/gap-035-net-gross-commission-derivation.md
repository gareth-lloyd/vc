# GAP-035 — Net↔gross rate entry with automatic commission derivation

- **Severity:** Gap (data-entry tooling; pricing flexibility).
- **Source:** 2026-06-17 owner Loom (pricing walkthrough, 2:40–3:21).
- **Files:**
  - `django_res/pricing/models/rate.py` (`RatePlan.price_basis`, `RateRule`
    `nightly`/`weekly`)
  - `django_res/properties/models/finance.py`
    (`PropertyFinance.effective_commission()`)
  - design: `django_res_design/04-pricing.md` (rate-entry), `10-decisions.md`
  - FE rate-band form (under
    `frontend/src/features/properties/tabs/PricingTab.tsx`)

## Problem

Owners supply rates as **either net or gross**. Today staff pick `price_basis`
and hand-enter a single figure; there is no tool to convert between the two. The
owner wants **both, with automatic derivation**: "if a client only gives us net
rates… we put in 20% commission and it automatically calculates the gross
amount and organises it accordingly" — and the reverse for gross (take the
commission off to get net).

**Single-source-of-truth risk with BUG-009:** if this tool *persists* a derived
gross figure while the (deferred) BUG-009 engine fix later carves
commission/tax back *out of* gross at quote time, the commission is applied
twice. The entry layer and the quote-time engine must agree on one canonical
stored figure.

## Proposed direction

An **entry-time** helper on the rate-band form that, given the band's net (or
gross) amount + the effective commission % (`effective_commission()`), derives
the counterpart for **display/convenience** while storing a single canonical
figure plus `price_basis` and the commission % used. Lean towards
**derive-on-display** (don't persist the computed side) to avoid the BUG-009
double-count.

Keep this **distinct from** the quote-time carve-out/gross-up of BUG-009 — this
is about what the operator types; BUG-009 is about how the engine interprets it
— but both must use the **same** net↔gross math (the legacy
`RatesModel.Calculate()` formulas already transcribed in BUG-009) so a band
entered here prices identically there.

## Open questions

1. Store the derived figure, or derive-on-display only? (Lean derive-on-display
   to avoid the BUG-009 double-count.)
2. Which commission source when property- and group-level differ? (Use
   `effective_commission()`'s resolution.)
3. Rounding direction on the derived figure — reuse the existing
   `quantise_money()` ROUND_HALF_EVEN policy (see `done/smell-003`); ties into
   Q-023.

## Acceptance

- Decision recorded in `10-decisions.md`; `04-pricing.md` rate-entry section
  updated with the derivation rule and the chosen storage model.
- FE rate-band form behaviour specced (which field is canonical, when the
  derived value recomputes).

## Dependencies

- **BUG-009** — must use the same net↔gross math and agree on the canonical
  stored figure (else double-counting).
- `PropertyFinance.effective_commission()`.
- Q-023 (rounding of the derived figure).
