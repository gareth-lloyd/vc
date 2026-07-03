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
2. **`sp_check_availability`** is invoked positionally at `ResService.cs:3205` — `ExecuteSelectCommand("sp_check_availability", param)` — so parameter order matters. Document the order in the Django port.
3. **`sp_getAvailability(@VillaId, @FromDate, @ToDate)`** — calendar-time soft check. Returns per-night status, joining `VillaAvailability` ↔ `AvailabilityStatus` ↔ `vw_properties`, and (all of this in a local `@temp_table` table variable scoped to the SP execution):
   - Filters out "available" rows (codes 10, 70) from the working set
   - Removes half-day records that have no same-status neighbour
   - Groups contiguous statuses into ranges (sequence number)
   - Returns: `Id`, `Status`, `StatusDate`, `UpdatedAt`, `CheckinTime`, `CheckoutTime`, `sequenceno`

### Outputs / side effects
- Read-only. The `DELETE` statements inside `sp_getAvailability` operate on a procedure-local `@temp_table` table variable (see `live-db-24-apr.sql:111935` for the declaration); the persistent `VillaAvailability` table is **not** mutated. An earlier audit pass flagged this as `[SIDE_EFFECT]`; that finding was **overturned** on direct inspection of the SP body.

### Open questions
- The intra-SP "remove orphan half-day" pass is procedural and slow (RBAR `WHILE` loop). The Django port should express the same shape declaratively (window functions over a daterange table, or compute it from `BookingHold` + `Booking` ranges directly).

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
