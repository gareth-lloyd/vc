# GAP-004 — Frontend placeholder tabs still showing "Coming Soon"

- **Severity:** Gap (frontend)
- **Source:** repo audit
- **Files:** `frontend/src/app/router.tsx`,
  `frontend/src/components/feedback/ComingSoonTab.tsx`

## Problem

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
