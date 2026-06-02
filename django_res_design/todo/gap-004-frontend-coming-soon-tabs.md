# GAP-004 — Frontend placeholder tabs still showing "Coming Soon"

- **Severity:** Gap (frontend)
- **Status:** ✅ **Resolved (2026-06-02)** — no placeholder tabs remain.
- **Source:** repo audit
- **Files:** `frontend/src/app/router.tsx`,
  `frontend/src/components/feedback/ComingSoonTab.tsx`

## Resolution (2026-06-02)

Verified stale. The tab set was trimmed from the original ~12-property
plan to a leaner set, and **every tab now in the config is fully built**:

- `PROPERTY_TABS` (`features/properties/tabConfig.ts`) = 9 slugs
  (details, rooms, nearby, features, pricing, people, availability, media,
  settings) — and `REAL_PROPERTY_TABS` (`app/router.tsx`) lists the **same**
  9.
- `BOOKING_TABS` (`features/bookings/tabConfig.ts`) = 8 slugs
  (overview, timeline, notes, payments, concierge, finance, owner, comms) —
  and `REAL_BOOKING_TABS` lists the **same** 8.

Because each config list equals its `REAL_*` set, `propertyPlaceholderRoutes`
and `bookingPlaceholderRoutes` both evaluate to **empty arrays**: not a single
route renders `ComingSoonTab`. The placeholder mechanism is wired but dormant —
fine to keep as scaffolding for any future tab.

The sub-resources the dropped tabs would have surfaced (finance, descriptions,
extras/discounts, collections, change-over rules) are folded into the existing
tabs, with backing endpoints already present — so nothing of value was lost.
Each *future* tab (if any is ever added) becomes its own ticket per the
follow-up below.

## Problem (original — now stale)

The router routes the property and booking detail pages through
`ComingSoonTab` placeholders for the tabs not in the `REAL_*_TABS` sets.
Today only ~8/12 property tabs and ~8/N booking tabs have real
implementations.

## Approach

Treat as a tracking ticket. The right order is driven by the canonical
journeys ([GAP-003](gap-003-endpoint-coverage-gap.md)), not the tab
ordering:

- Booking → Concierge tab is needed for journey 3 (cancellation /
  refund) since the concierge items affect the refund calculation.
- Booking → Comms tab is the read surface for the comms work in
  [GAP-001](gap-001-comms-empty-url-surface.md).
- Property → Pricing / Availability tabs back journey 5 (portfolio
  season setup).

## Follow-up

Each tab becomes its own ticket once the backing endpoints exist.

## Dependencies

[GAP-001](gap-001-comms-empty-url-surface.md), the backend tab
endpoints, and the product questions blocking each journey.
