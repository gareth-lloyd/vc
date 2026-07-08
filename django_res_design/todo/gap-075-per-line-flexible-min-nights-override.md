# GAP-075 — Per-quote-line ad-hoc flexible stay (min-nights + nightly)

- **Severity:** 🟢 Gap (new per-line override). Cross-stack.
- **Source:** 2026-07-08 Nick / Gareth res-rebuild call. Nick: even villas with
  an official fixed changeover will, late in the season or when gaps appear,
  "go flexible from now on, with a minimum" — staff need to offer a flexible
  nightly stay on a *specific quote* without changing the property's standing
  changeover config.
- **Files touched (best-guess):**
  - `django_res/reservations/models/quotation.py` — `QuotationLine` (~L220-278)
    has no `is_flexible` / `min_nights` / nightly fields; the only escape hatch
    is `is_manual` + operator-typed `total` + `price_override_reason` (a flat
    figure, not a nightly rate or a date-range-with-min-nights construct).
  - `django_res/reservations/services/stay_options.py` /
    `django_res/pricing/services/engine.py` — reprice path; min-nights today is a
    property/period concept only (`PropertySettings.min_nights_rental`,
    `RatePeriod.min_nights`, strictest-wins in `_validate_periods_against_stay`).
  - `frontend/src/features/quotations/` — `schemas.ts`
    (`quotationLineWriteInputSchema` ~L387), `StayOptionPicker.tsx` /
    `QuoteResultLine.tsx`, `SaveQuoteDialog.tsx`.

## Problem

There is no way to mark a single quote line as "flexible arrival, min N nights,
priced nightly" independent of the property's changeover day. Min-nights is a
property/period concept; the only per-line override is a flat manual total —
no nightly rate, no min-nights, no date-range semantics.

## Proposed fix

- Add an operator affordance on a fixed-changeover result to "quote flexibly"
  for this stay: sets a per-line flag + min-nights, then prices via the
  [GAP-074](gap-074-nightly-price-quoting-no-changeover.md) nightly-range path
  within the true available window (respecting the ad-hoc min-nights, not the
  property changeover).
- Persist the flag + min-nights on `QuotationLine` (nullable, default off) so
  the saved quote and its email render as a nightly/flexible option.
- The reprice contract carries the override so the engine ignores changeover
  alignment for that line only; all other quotes and the property config are
  untouched.

## Acceptance

- An operator can flip a fixed-changeover result to a flexible nightly quote
  with a min-nights, priced within the true available window, without touching
  property config. (component + service test)
- The property's standing changeover behaviour and every other quote are
  unaffected. (test)
- Quality gate green both stacks.

## Dependencies

- Depends on **GAP-074** (nightly-range renderer + engine path).
- Related **SMELL-024** (QuotationLine / quotation-view god-object — keep the
  override thin).
