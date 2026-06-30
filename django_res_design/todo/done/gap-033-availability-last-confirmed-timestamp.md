> **✅ RESOLVED (2026-07-01)** — Shipped on local `main` (unpushed) via
> feat/gap-033 (Unit 1 `1c592b2`, Unit 2 `c0e7d68`, Unit 3 `4905df0`, Unit 4
> `bbd4fb9`, Unit 5 `c82b6b2`, Unit 6 `fb2baaf`, Unit 7 `1c5e18b`).
> **Superseded the single-field proposal** with a deliberate three-signal split,
> so the sales UI never conflates "an owner changed their calendar" with "a VC
> staffer vouched it's accurate": **(1) Updated by owner** —
> `Property.availability_owner_updated_at`, touched from `OwnerBlockService`
> create/release (MANUAL only); **(2) Last calendar import** — derived in-app
> from `PropertyCalendarFeed.last_polled_at` via a scalar `Subquery`
> annotation, shown only when a feed exists; **(3) Confirmed by VC staff** —
> `availability_confirmed_at` + `availability_confirmed_by`, written only by the
> new `POST /properties/{id}:confirm-availability` action (IsReservationsWriter).
> Signal 1 is **stored** (not derived) because the import-linter spine forbids
> `properties → reservations`; storing on `Property` + writing down-spine keeps
> the read a plain column. Touching only on create/release means staff
> `contest()` (which bumps the block's `updated_at`), iCal churn, and
> quotation/booking holds are all excluded — tested both ways. The freshness
> touches deliberately do **not** bump `Property.updated_at`. FE: three labelled
> lines + a "Mark as up-to-date" button on the Availability tab (shown for all
> villas), and read-only freshness badges on the multi-villa timeline; en+el.
> **Deferred:** an actor for Signal 1 (date-only), a separate
> `AvailabilityConfirmation` history model, a confirm button on the wide
> timeline (badges only), and GAP-034 coordination on auto-deriving "confirmed"
> for iCal villas.

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
