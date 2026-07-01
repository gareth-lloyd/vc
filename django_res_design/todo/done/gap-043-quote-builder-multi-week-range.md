> **✅ RESOLVED (2026-07-02)** — Shipped on `feat/gap-043` (6 units,
> `8512ee3`…`7f3b7a7`): the builder search form was **replaced** with the
> mockup's range shape (Arrive from + Arrive to + Number of weeks + Search
> Specific Date), translated client-side onto the unchanged `search-options`
> contract (`flex = ceil(W/2)`, midpoint preferred arrival; 42-day window cap
> = 2 × SEARCH_FLEX_MAX — **no backend change**). `StayOptionPicker` became a
> multi-select checkbox group (held weeks stay non-selectable per 2026-07-01);
> every ticked week stages its own line (`StagedLine.line_id =
> property:date_from`) and save fans out **weeks × checked occupancy bands**.
> Enquiries seed the window symmetrically (`date_from ± flexibility_days`).
> **Deferred:** `flexibility_days` widening + "Flexible" enum → GAP-050 item 7 (the
> builder window already runs to ±21 days without it). **Accepted v1 limits:**
> flexible/no-fixed-changeover villas have no week strip → single-week line at
> the criteria dates (GAP-025/Q-022 deferral, H1); the occupancy band-check is
> **shared across ticked weeks** by party-range identity, not a per-week 2D
> grid (M2). Docs: `05-reservations.md` §"Date flexibility on intake"
> resolution note + new `10-decisions.md` row.

# GAP-043 — Quote builder: multi-week date-range selection

- **Severity:** Gap (frontend + backend) — quote-builder rework; **reverses a
  prior decision** (flagged below)
- **Source:** 2026-06-17 owner Loom ("it's a fixed price, fixed dates … this is
  not correct … we do a date range … click all the weeks we want to quote") +
  the mockup at https://vc-new-res-system.netlify.app/ → **Rate Lookup**.
  Mirrors the legacy `QuoteGenerator`/`RateLookup` weeks model in
  [GAP-010 §4](../gap-010-quote-enquiry-analyzed-wrong-codebase.md).
- **Status:** Open — **replace-vs-coexist is an open question** (see Tension).
- **Files:**
  - `frontend/src/features/quotations/QuoteCriteriaForm.tsx`,
    `QuoteBuilder.tsx`, `QuoteResultsList.tsx`, `StayOptionPicker.tsx`
  - `django_res/pricing` `:search-options` endpoint;
    `reservations/models/enquiry.py` (`flexibility_days` widening)

## Problem

The builder currently quotes **fixed dates** (`date_from`/`date_to`) plus a small
`flexibility_days` (0–3) stepper. The owner says this is wrong: clients rarely
want a single fixed week, and even fixed-date clients are often quoted a range
for availability. He wants to search a **date range** and tick **every week** to
quote, per property.

## Proposed fix

Adopt the mockup's Rate Lookup shape:

- Search by **Arrive Date + Arrive Date-to** (a window of candidate arrival
  dates) + **Number of Weeks**, with a **"Search Specific Date"** toggle for the
  exact-date case (legacy `IsSpecificDate`).
- Results render, per property, a set of **week boxes** — each with a
  **checkbox**, the week's price, and an availability badge
  (Available / Unavailable / on-hold + "Remove hold"). The agent ticks the weeks
  to include; ticked weeks build the quote ("builds down the bottom", which the
  owner liked). **Held/booked weeks stay non-selectable** — the shipped
  single-select `StayOptionPicker` disables a held cell and skips it in keyboard
  nav (2026-07-01, see `10-decisions.md`); carry that into the multi-week model
  so a booked week isn't tickable, and freeing it routes through the explicit
  "Remove hold" action rather than by making the booked week directly selectable.
- Keep changeover handling via the existing engine auto-shift
  ([GAP-007](gap-007-changeover-autoshift-parity.md)).

## Tension to resolve (do not silently overwrite)

1. **Reverses the 2026-06 date-flexibility rework.** `05-reservations.md`
   §"Date flexibility on intake" deliberately *removed* date-range quoting in
   favour of true requested dates + `flexibility_days` (its rationale: eliminate
   the destructive date-shift). Multi-week range quoting brings the range back.
   **Leave replace-vs-coexist open in build:** a range/calendar picker may
   *replace* the stepper, or *coexist* (stepper for the tight ±N case, range for
   wide multi-week). The spec note records the tension; the implementer decides
   with UX.
2. **Flex vocabulary is wider than today.** The mockup's Flex? values are
   `Specific dates` / `+/- 3 days` / `+/- 7 days` / `Flexible`, exceeding the
   current `flexibility_days` 0–3 cap. Widen the cap and add an open **Flexible**
   mode; align the enum with [GAP-039](gap-039-enquiry-dashboard-enrichment.md).

## Acceptance

- The builder searches a date range + weeks; per-property week boxes are
  individually checkable and the ticked weeks form the quote.
- Flex values match the agreed vocabulary; changeover shift still applies.
- The replace-vs-coexist decision is recorded; `flexibility_days` widening has a
  migration + tests.
- Quality gate green.

## Dependencies

- [GAP-044](gap-044-occupancy-band-fanout-builder.md) (occupancy lines render
  inside these week boxes), [GAP-013](../gap-013-quote-builder-ux-feedback-loops.md)
  and [GAP-005](../gap-005-quotation-flow-parity.md) #9 (builder shape) — coordinate
  so the builder isn't reworked twice. Spec amendment:
  `05-reservations.md` §"Date flexibility on intake".
