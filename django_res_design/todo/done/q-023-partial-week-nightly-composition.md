# Q-023 — Partial-week / nightly price composition for odd-length stays

> **✅ SUPERSEDED (2026-09-16) — merged into [GAP-074](../gap-074-nightly-price-quoting-no-changeover.md)** as
> §"Merged from Q-023". Q-023's composition rule is what GAP-074/075 render, and its D1–D3 confirmations were already moved onto GAP-074's owner call (2026-07-29). Nothing was decided or built by the
> merge; the open work continues there.
>
> _Original ticket preserved below for context._

- **Severity:** Question (pricing correctness for non-whole-week stays).
- **Source:** 2026-06-17 owner Loom (pricing walkthrough, 3:21–4:01).
- **Files:**
  - `django_res/pricing/services/rates.py:23` (`rule_nightly` —
    `nightly = weekly/7` derivation, the single derive point)
  - `django_res/pricing/services/engine.py` (per-night line assembly)
  - `django_res/pricing/models/rate.py` (`RateBand.nightly`/`weekly`)
  - design: `django_res_design/04-pricing.md` (engine steps), `10-decisions.md`

> **2026-07-29 refresh:** `RateRule` is now `RateBand` (SMELL-019), and Q-018
> added base + reduction fields with derived `effective_*` — all still quoted
> through the same `rule_nightly` derive point, so the composition question
> below is unchanged. **Overlap note:** GAP-074/075 build the nightly *output*
> path (nightly-range quoting for no-changeover / ad-hoc-flexible villas);
> this ticket's D1–D3 confirmation questions should ride the GAP-074
> owner/Debbie call rather than a separate ask — see
> [gap-074](../gap-074-nightly-price-quoting-no-changeover.md) and
> [owner-questions-2026-07-02.md](../reviews/owner-questions-2026-07-02.md).

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
- Confirm whether an explicit `RateBand.nightly` always **wins over** the
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

- Existing `nightly`/`weekly` on `RateBand`; `rule_nightly`
  (`pricing/services/rates.py:23`).
- `done/smell-003` (rounding — reuse, don't reopen), `done/gap-008`
  (`fallback_nightly`).
- GAP-035 (rounding of the derived net↔gross figure); Q-018 (base+reduction —
  resolved; effective prices derive through `rule_nightly`).
- [GAP-074](../gap-074-nightly-price-quoting-no-changeover.md) /
  [GAP-075](gap-075-per-line-flexible-min-nights-override.md) — the nightly
  quoting surfaces this composition rule feeds.
