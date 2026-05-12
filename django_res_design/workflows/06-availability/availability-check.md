# Availability Check

Read-side queries used by quotation building.

## Check availability for date range

**ID:** `AVAILABILITY.CHECK.RANGE`
**Trigger:** Called inside the pricing engine (`PRICING.ENGINE.COMPUTE_QUOTATION`) and inside booking save (`BOOKING.LIFECYCLE.CREATE_FROM_QUOTATION`).
**Actor:** System.
**Legacy locus:** `ResService.cs:3205` (booking validation), `ResService.cs:2200-2203` (pricing engine).

### Inputs
- `VillaId`, `FromDate`, `ToDate`
- For booking save also: `BookingId` (so the engine doesn't count the booking-being-edited as a conflict with itself)

### Process
There are **two** SPs in play:

1. **`sp_check_availability(@FromDate, @ToDate, @VillaId, @BookingId)`** — booking-time hard check. Returns rows when an overlapping booking/hold exists.
2. **`sp_getAvailability(@VillaId, @FromDate, @ToDate)`** — calendar-time soft check. Returns per-night status, joining `VillaAvailability` ↔ `AvailabilityStatus` ↔ `vw_properties`, and:
   - Filters out "available" rows (codes 10, 70) — only returns the blocked/booked subset
   - Deletes half-day records that have no same-status neighbour (cleanup pass)
   - Groups contiguous statuses into ranges
   - Returns: `Id`, `Status`, `StatusDate`, `UpdatedAt`, `CheckinTime`, `CheckoutTime`

### Outputs / side effects
- Read-only on the rows themselves — but the cleanup pass in `sp_getAvailability` does mutate (`DELETE` half-day rows). `[SIDE_EFFECT]` from a read.

### Open questions
- `sp_getAvailability` mutating data on a read call is unsafe and surprising. The redesign should keep cleanup separate from query.

---

## Update last-updated timestamp

**ID:** `AVAILABILITY.CHECK.RESET_LAST_UPDATED`
**Trigger:** Admin clicks "Update" button next to the last-updated label.
**Actor:** Staff.
**Legacy locus:** `ResService.cs:3538-3553` (`ResetLastUpdated`); SP `sp_last_update_at`.

### Inputs
- `propertyId`

### Process
1. Execute `sp_last_update_at @propertyId`.

### Outputs / side effects
- A timestamp is bumped (likely on a tracking table — SP body not in committed code). The "last published to external systems" semantic is implied.
- Toast "Last update is successfully saved!".

### Open questions
- Decide what "last updated" semantically means in the redesign: last DB mutation? last sync to WordPress? Both should be expressible separately.
