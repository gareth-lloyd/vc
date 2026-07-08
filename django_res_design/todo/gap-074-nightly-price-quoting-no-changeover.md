# GAP-074 — Nightly-price quoting for no-fixed-changeover villas

- **Severity:** 🟢 Gap (new quoting surface) — the per-night data exists in the
  engine, but no output path renders it. Cross-stack (backend stay-options + FE
  builder + guest email).
- **Source:** 2026-07-08 Nick / Gareth res-rebuild call. Nick: Kenya / Patmos
  villas have no fixed changeover; the best way to sell them is to give the
  client the **full available date range + a nightly price** and let them do
  their own date maths — possibly with **multiple price bands** across the range
  where rate periods change. ~95% of quotes stay weekly blocks; this is the
  minority path.
- **⚠️ Product gate — needs owner/Debbie call before build.** Nick wants to run
  the two-tier (weekly-block *vs* nightly) presentation past Debbie: the concern
  is guest confusion when one quote mixes weekly-priced and nightly-priced
  options. Also open: is nightly the *default* for no-changeover villas or an
  opt-in, and do we standardise all options in an email to one style?
- **Files touched (best-guess):**
  - `django_res/reservations/services/stay_options.py` — `StayOptionsService`;
    no-changeover branch prices the requested dates as-is (`_plan_blocks`
    returns `[], 0, None` when `ChangeoverService.required_weekday()` is `None`,
    ~L392); `weekly_prices` explicitly *defers* flexible villas (returns
    `changeover_day=None, weeks=[]`, ~L434).
  - `django_res/pricing/services/engine.py` — engine already yields one
    `QuoteLine(nightly=…)` per night (~L161-208); `RateBand.nightly` /
    `RatePlan.fallback_nightly` supply per-night rates.
  - `django_res/reservations/services/quotation_render.py` — email/preview
    context; today emits `nights` + block `total` per line, no nightly rate
    (~L104-116).
  - `frontend/src/features/quotations/` — `schemas.ts` (`stayOptionSchema` /
    `quoteOptionSchema` parse `total`/`nights`, no per-night field),
    `QuoteResultLine.tsx`, `StayOptionPicker.tsx` (week strip).
  - `django_res/comms/templates/comms/quotation.sent.body.mjml` — per-line row.

## Problem

For a `changeover_day = any` property, the builder can only quote the exact
requested dates as a single option; there is no way to present "available from
D1 to D2, £X / night" and let the client pick their own dates. Every consumer
renders a block/stay **total** — the nightly rate is computed by the engine but
never surfaced — and `weekly_prices` skips flexible villas, so the timeline
strip is blank for them too. Nick's preferred sell for these villas (whole
available range + nightly price, banded across rate periods) is unbuildable
today.

## Proposed fix

1. Add a nightly-range stay option to `StayOptionsService` for no-changeover
   villas (and, once [GAP-075](gap-075-per-line-flexible-min-nights-override.md)
   lands, any line flagged flexible): resolve the maximal available window
   around the requested dates, split it at `RatePeriod` boundaries into one or
   more nightly-priced segments (reuse the canonical flattener /
   `covering_bands`), each carrying `nightly`, `date_from`, `date_to`, `nights`,
   `currency`, POA flag.
2. Extend the `search-options` contract + FE schemas with a `nightly_range`
   option kind alongside the existing block options; render it in
   `QuoteResultLine` as a date-range row with a per-night price (multiple
   sub-rows when the range spans price bands).
3. Extend the quote line + render context so a saved nightly-range line emails
   as "Available DD Mon – DD Mon · £X / night" (multi-band → multiple lines),
   grouped under the flexible/nightly section from
   [GAP-078](gap-078-quote-property-ordering-country-region.md).
4. Presentation decision (product): standardise all options in an email to one
   style, or show a weekly-block vs nightly section break (see GAP-078).

## Acceptance

- A no-changeover property in the builder offers a nightly-range option showing
  the full available window + per-night price, split into segments where rate
  periods change. (service + component test)
- Saving it stores a nightly-priced line that renders in the quote email with a
  nightly rate and date range. (test)
- Weekly-block villas are unaffected; the engine single-block contract is
  unchanged.
- Quality gate green both stacks.

## Dependencies

- **Product:** owner/Debbie call on two-tier presentation — blocks build.
- Sibling of **GAP-075** (per-line flexible/min-nights override; the ad-hoc
  late-season case reuses this nightly-range renderer).
- Builds on **GAP-030** (weekly-prices timeline — extend to flexible villas) and
  **Q-023** (partial-week / nightly composition; rounding + fallback already
  done).
- Feeds **GAP-078** (section grouping weekly vs nightly).
