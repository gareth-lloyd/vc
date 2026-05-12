# 06 · Availability

The per-night availability calendar for each property. One row per (property, date), with a status code. The same table records bookings, holds, manual blocks, and "available" markers.

## Files

| File | Workflows |
|---|---|
| [`calendar-view.md`](./calendar-view.md) | Load availability calendar, fetch last-updated timestamp, reset last-updated timestamp |
| [`availability-check.md`](./availability-check.md) | Check availability for a date range (called by quotation flow) |
| [`holds.md`](./holds.md) | Create hold on quotation save, auto-expire hold (scheduler) |
| [`booking-status-transitions.md`](./booking-status-transitions.md) | Hold → Booked on booking confirmation; Booked → Available on cancellation |
| [`blocks-and-changeover.md`](./blocks-and-changeover.md) | Manual block (stub), changeover-day enforcement (partial) |

## Status code reference

The legacy system uses small magic integers for availability status. They appear throughout the codebase and SPs.

| Code | Meaning | Source |
|---|---|---|
| 10 | Available | Default; not stored as a row, implied by absence |
| 20 | Available – Enquire | Available but require enquiry-first flow |
| 30 | Unavailable | Manual block |
| 40 | On Hold | Temporary 7-day hold from a quotation |
| 50 | Booked | Confirmed booking |
| 60 | Booked – VC | Internal VC-owned booking |
| 6 | Booked – Ext | External system booking (channel manager) |
| 70 | Available (Again) | Released — historically blocked, now available |

The Django redesign should turn these into named `TextChoices` and drop the magic numbers.

## Entities touched

- `VillaAvailability` — one row per (property, available-date) with status. `StartDate`/`EndDate` capture the original range that produced the row; `Notes`, `QuotationNo`, `CreatedAt`/`CreatedBy`/`UpdatedAt`/`UpdatedBy`.
- `AvailabilityStatus` — lookup of status codes
- `ChangeOverDays` — lookup of changeover days-of-week
- `VillaMaster.SettingCheckInTime` / `SettingCheckOutTime` / `SettingChangeoverDayId` / `AvailabilityType` / `AvailabilityValue`

## Stored procedures

- `sp_villaAvailability` — write per-night rows for a range (handles existing-row deletes, range expansion via `master.dbo.spt_values` `[SQL_QUIRK]`, status update)
- `sp_check_availability` — validate booking range against existing rows
- `sp_getAvailability` — fetch per-night status for a calendar render
- `sp_last_update_at` — write a "last-updated" timestamp

## Known stubs and gaps `[STUB]`

Per `ResSystem/LOCAL.md` and the investigation:

- **`AvailabilityCard.razor`** component — placeholder. The interactive calendar UI was withheld from the repo. The legacy code has ~400 lines of commented half-day rendering logic — sophisticated boundary-night styling (e.g., `booked-before`/`hold-after`).
- **`AvailabilityData.cs`** — stub class with skeleton properties.
- **Manual block creation/editing** — no UI, no service method captured.
- **Changeover-day enforcement** — `ChangeOverDays` is read but never enforced. A guest can book a non-changeover arrival without warning.

## Open design questions for the Django redesign

- **Per-night storage** (~365 rows/year/property) vs **range storage** (one row per booking/hold/block). Range storage with a daterange + `EXCLUDE` constraint is more compact and naturally enforces non-overlap. The downside is range queries are slightly more complex.
- The redesign (`../06-availability.md`) plans range-storage with PostgreSQL `daterange` + `EXCLUDE USING gist`. That's the right call.
- **Hold expiry** should be a Celery beat task or a `select_for_update`-driven sweep — not a hand-rolled scheduler.
- **Changeover-day enforcement** should be an explicit validation point in the booking workflow, not a passively-readable property attribute.
- **External availability source** (`AvailabilityType=URL` / `AvailabilityValue={url}`) is captured as a string but never fetched — design intent unclear.
