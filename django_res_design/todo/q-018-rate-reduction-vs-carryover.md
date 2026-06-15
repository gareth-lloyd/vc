# Q-018 — Rate reductions: base price + reduction, so carry-over copies the base

- **Severity:** Question (design decision; carry-over correctness at stake)
- **Source:** 2026-06-11 new-villa setup transcript review
- **Files:** `pricing/models/rate.py` (`RateRule`),
  `django_res_design/04-pricing.md` (`RateCarryoverService.materialise()`,
  ~line 239), `pricing/models/discount.py`

## Problem

Today (legacy and new alike), a mid-season rate reduction is done by
**overwriting the price**. The loader then leaves a free-text note ("rate
reduced by 10% on 10 June") purely so that, when copying rates to next
season, she remembers to revert to the original — "the owners won't want
us copying over the reduced rates for the next season."

The new `RateCarryoverService.materialise()` clones the anchor year's
rules verbatim. If 2026 was discounted in place, **2027 inherits the
discounted price** — exactly the failure she manually guards against.
Her own design suggestion from the transcript: "keep the original price
and then apply a reduction to it."

The existing `Discount` model is promo-code/auto-apply oriented, not a
per-rate-rule price reduction, so it doesn't cover this as-is.

## Proposed direction

Model the reduction on `RateRule`: keep `nightly`/`weekly` as the **base**
price and add reduction fields — support **both** a `reduction_percent`
**and** a `reduction_amount` (fixed new amount), plus `reduced_at` and an
optional reason. The pricing engine
quotes the reduced price; carry-over copies the base and drops the
reduction. The free-text `notes` ritual disappears.

## Open questions (for the loader / product)

1. ~~Is a reduction always a % off the whole band, or sometimes a fixed
   amount or specific weeks only? (Specific weeks → split the band rather
   than complicate the model.)~~ **Answered** (Nick/Bryony, 2026-06-11
   email): a reduction is *usually* a % off certain still-available weeks,
   but *sometimes* a fixed (new) amount — "both options please" (Nick wants
   maximum pricing flexibility). So the model must support **both** a
   percentage reduction and a fixed-amount reduction, scoped to specific
   weeks/bands; for specific weeks → split the band. The customer also
   confirmed the base-price + reduction approach (so carry-over copies the
   base) is correct.
2. Does a reduction apply to new bookings only from its date? (Engine
   quotes are point-in-time, so probably yes by construction — confirm.)
3. Should sales see "reduced from X" in the quote builder, or just the
   effective price?

## Acceptance

- Decision recorded in `10-decisions.md`; `04-pricing.md` updated.
- If adopted: model fields + engine support + carry-over uses base price,
  with tests pinning "discounted 2026 → undiscounted 2027 carry-over".

## Dependencies

Interacts with `RateRule.is_locked` semantics and GAP-023 (rate badges).
