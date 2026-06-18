# GAP-033 — Availability "last confirmed" timestamp + manual confirm button

- **Severity:** Gap (legacy-parity; sales-team trust signal)
- **Source:** owner Loom walkthrough 2026-06-17 (availability section, 1:46–2:25):
  "this is an important one… we have last updated. Every time the availability is
  updated this resets. If the availability is correct, we also have an update
  button here, which should reset this date without actually adding new dates;
  obviously, if new dates are added then it will update the last updated
  automatically."
- **Files (new):** a per-property freshness timestamp + actor — confirmed absent
  today (`properties/models/settings.py`, `properties/models/*` carry no
  `availability_confirmed_at`/`last_confirmed`). Surfaces:
  `frontend/src/features/availability/AvailabilityTimelinePage.tsx`,
  `frontend/src/features/properties/tabs/AvailabilityTab.tsx`.

## Problem

Legacy shows a per-property "last updated" date for availability, plus an
**"Update" button** that lets staff confirm availability is still current
**without adding any dates**. Adding dates updates it automatically. This tells
sales how fresh the owner-sourced availability is. The new system has no such
marker for manual availability — only `PropertyCalendarFeed.last_polled_at`
exists, and only for iCal feeds (and it isn't surfaced).

## Central design question (settle before building)

What counts as an "availability update" that resets the timestamp? It tracks
**owner-availability freshness**, so it must fire on:

- owner blocks created/edited/released (`OwnerBlock` / `source=MANUAL` stop-sale
  / maintenance holds),
- the explicit manual **confirm** action,
- an iCal sync that changed blocks (see GAP-034 / GAP-011).

It must **NOT** fire on VC quotation holds (`reason=QUOTATION_OPEN`) or VC
booking conversions — those are internal VC churn, and resetting on them would
make the signal reset every time sales builds a quote, destroying its meaning.

Lean to **intent over strict legacy mechanic**: this is internal-/sales-facing,
so modernising the mechanic (a single per-property timestamp, scoped to the
events above) is allowed rather than reproducing the legacy field verbatim.

## Proposed fix

- Add a per-property `availability_confirmed_at` (DateTimeField) + actor (no soft
  delete — a plain timestamp, consistent with conventions). Field home is open:
  `Property` vs `PropertySettings`.
- Auto-touch it from the owner-availability events listed above (service layer,
  not signals on every hold).
- Add an endpoint + an **"Update / Confirm"** button that touches the timestamp
  **without adding dates** ("checked with owner, still accurate").
- Surface the timestamp in the sales timeline and the property availability tab.

## Open questions to capture

- Field home: `Property` vs `PropertySettings`.
- For iCal-synced villas, do we auto-derive freshness from
  `PropertyCalendarFeed.last_polled_at` and hide the manual confirm, or keep both?
  (Coordinate with GAP-034.)

## Acceptance

- A per-property availability freshness timestamp exists and is shown in the
  sales timeline + property availability tab.
- Owner-block create/edit/release and the manual confirm action touch it; VC
  quotation holds and booking conversions do **not** (test both ways).
- The "Update / Confirm" button refreshes the timestamp without creating dates.

## Dependencies

GAP-034 (iCal-synced villas / freshness source), GAP-011 (`last_polled_at`).
