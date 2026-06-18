# GAP-030 — Show weekly pricing in the sales availability timeline

- **Severity:** Gap (designed-but-unbuilt; sales-team UX)
- **Source:** owner Loom walkthrough 2026-06-17 (availability section, 0:30–1:04):
  "what we're missing is pricing… it would be great to get pricing in some of
  these. Now these will be mostly in week-long blocks, so I think price by week,
  which is the default, would be preferable… we'll always also be able to see the
  changeover there."
- **Files:** `frontend/src/features/availability/AvailabilityTimelinePage.tsx`,
  `TimelineGrid.tsx`, `frontend/src/features/availability/{api.ts,hooks.ts,schemas.ts}`;
  backend `reservations/services/stay_options.py` (`StayOptionsService`),
  `reservations/views/quote_options.py`, `pricing/views/quote.py`
  (`PricingQuoteBulkView`).

## Problem

The sales-team multi-villa timeline (`/availability`) shows availability bands
(bookings / holds / stop-sale) but **no price**. When sales are on the phone with
a client they can talk through what's free but have to look pricing up separately.
The owner wants a price shown inline — defaulting to **price by week**, since
stays are mostly week-long blocks — with the **changeover day visible** alongside
it.

## MVP scope (this is where the owner's own deferral bites)

"Price by week" across a ~5-week timeline window is **not a single number** — the
weekly rate varies week to week and can cross rate bands. The owner explicitly
parked the hard cases ("there will be complexities once we get into variable
changeovers and pricing blocks which aren't in a strict week, but we can get into
that").

- **In scope:** villas with a **fixed changeover day** show a price **per
  changeover-anchored week-block** in their row, with the changeover weekday
  visible.
- **Deferred (note as future, cross-ref GAP-025, Q-022):** flexible-changeover
  villas (`changeover_day = ANY`), variable changeovers within a window, and
  pricing blocks that aren't a strict week.

## Proposed fix

**Backend — reuse the existing changeover-aware pricing, don't reinvent.**
`StayOptionsService` (`reservations/services/stay_options.py`, already exposed at
`POST /quotations:search-options`) already prices **changeover-to-changeover
whole-week blocks** for fixed-changeover villas (and returns a single option for
flexible ones) using `PricingEngine` + `resolve_property_currency`. Extend/wrap
it (or add a thin sibling) to return the per-week guide price for each
changeover-anchored week intersecting the timeline window, for a batch of
properties. Lower-level engine batching is available via `PricingQuoteBulkView`
if a leaner path is wanted.

- Surface the **projected/guide** distinction (`Quote.is_projected`) so a derived
  (no-plan-for-year) price reads as a guide, not a firm quote.
- Handle `is_poa` → "POA" and no-rate → the existing incomplete-pricing flag
  (resolved Q-013), not a hard error.
- Currency display per **GAP-026** conventions (from `RatePlan.currency_code`).

**Frontend.** Add a per-week price to each row in `TimelineGrid.tsx` (new field in
the availability `schemas.ts` / `api.ts` / `hooks.ts`), aligned to the
changeover-anchored week-blocks, with the changeover weekday shown per villa.

## Acceptance

- Each timeline row for a **fixed-changeover** villa shows a weekly price per
  changeover-anchored week intersecting the window, with the changeover weekday
  visible.
- Derived/no-plan prices are flagged as a guide (`is_projected`); POA and
  incomplete-pricing villas render the existing flags, never a 500.
- Currency is shown per GAP-026 (from the rate plan's `currency_code`).
- Flexible-changeover / variable-changeover / sub-week pricing is explicitly out
  of scope and documented as deferred.
- Pricing for up to the 50-property page reuses the bulk/`StayOptionsService`
  path (no N×weeks per-villa engine calls per load); a Vitest/pytest pair covers
  the week-block price mapping.

## Dependencies

- **Reuses:** `StayOptionsService` / `POST /quotations:search-options`,
  `PricingQuoteBulkView`, `resolve_property_currency`.
- **Related:** GAP-025 (changeover-aware rate-band dates), GAP-026 (currency
  display), Q-013 (incomplete-pricing flag — resolved), Q-018 (rate reductions),
  Q-022 (seasons defined by rates). The "see the changeover" piece could spin out
  if it grows beyond a display weekday.
