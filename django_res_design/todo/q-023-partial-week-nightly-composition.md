# Q-023 — Partial-week / nightly price composition for odd-length stays

- **Severity:** Question (pricing correctness for non-whole-week stays).
- **Source:** 2026-06-17 owner Loom (pricing walkthrough, 3:21–4:01).
- **Files:**
  - `django_res/pricing/services/rates.py` (`rule_nightly` —
    `nightly = weekly/7` derivation)
  - `django_res/pricing/services/engine.py` (per-night line assembly)
  - `django_res/pricing/models/rate.py` (`RateRule.nightly`/`weekly`)
  - design: `django_res_design/04-pricing.md` (engine steps), `10-decisions.md`

## Problem

Pricing is week-block oriented; the owner needs **nightly pricing for "odd
bookings over 10–15 days outside the week block"** and is worried about
**decimals / rounding up or down**.

Two of his three concerns are **already resolved**:
- Money rounding policy is `quantise_money()` / ROUND_HALF_EVEN
  (`done/smell-003`).
- No-rate-for-a-night fill is `RatePlan.fallback_nightly` (`done/gap-008`).

The genuinely-open piece is the **partial-week composition rule**: how a stay
that isn't a whole number of weeks is built from `weekly` and `nightly` rows.
Today the engine prices **per night** — deriving `nightly = weekly/7` (quantized
to 0.01) when only `weekly` is set — and sums the nights. The question is
whether that matches owner expectation, versus, e.g., N×weekly + remainder
nights at an explicit nightly rate.

## Proposed direction

Document the partial-week algorithm explicitly in `04-pricing.md`:
- Confirm whether an explicit `RateRule.nightly` always **wins over** the
  `weekly/7` derivation for sub-week remainders.
- State how full-week + remainder stays combine (per-night sum vs
  N×weekly + remainder×nightly).
- Keep rounding on the **existing** ROUND_HALF_EVEN per-night policy — do **not**
  re-open `smell-003`. Frame the owner's rounding worry as "verify the current
  policy meets expectation," not "define a new one."

## Open questions

1. Per-night quantize-then-sum (current behaviour) or quantize-the-stay-total?
2. Does an explicit `nightly` override `weekly/7` for sub-week remainders?
3. Any minimum-night threshold before nightly pricing applies?

## Acceptance

- Decision recorded in `10-decisions.md`; `04-pricing.md` engine steps state the
  partial-week composition rule.
- Engine tests pin a representative 10- and 15-night partial-week quote.

## Dependencies

- Existing `nightly`/`weekly` on `RateRule`; `rule_nightly`
  (`pricing/services/rates.py`).
- `done/smell-003` (rounding — reuse, don't reopen), `done/gap-008`
  (`fallback_nightly`).
- GAP-035 (rounding of the derived net↔gross figure); Q-018 (band splitting).
