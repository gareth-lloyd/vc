# Booking-driven Availability Transitions

The calendar transitions that fire as a side-effect of booking lifecycle events.

## Hold → Booked on booking save

**ID:** `AVAILABILITY.TRANSITION.HOLD_TO_BOOKED`
**Trigger:** Booking save / create from quotation (see `09-booking/booking-creation.md`).
**Actor:** System.
**Legacy locus:** `ResService.cs:3242-3249` — called inside the booking save path.

### Inputs
- From the booking save: `QuotationNo`, `FromDate`, `ToDate`, `VillaId`, `UserId`, plus the new `BookingId`.

### Process
1. `ModifyVillaAvailability(new PropertyStatus { Action='UPDATE', FromDate, ToDate, QuotationNo, Status=50, Notes="Update from BookingModify by {UserId} : {User Email}", User, VillaId })`.
2. SP `sp_villaAvailability` applies the now-familiar delete-existing/insert-missing/update pattern, flipping status to 50 (Booked).

### Outputs / side effects
- **DB write:** `VillaAvailability` rows in the range flip 40 → 50.
- Subsequent reads see the dates as Booked.

### Failure modes
- Race: if the hold has already auto-expired (status 70), the SP still works — it overwrites status 70 to 50.

---

## Booked → Available on booking cancellation

**ID:** `AVAILABILITY.TRANSITION.BOOKED_TO_AVAILABLE`
**Trigger:** Booking deletion / cancellation (see `09-booking/booking-cancellation.md`).
**Actor:** System.
**Legacy locus:** `ResService.cs:913-931` (`DeleteBooking`).

### Inputs
- `BookingId`, `QuotationNo`, `FromDate`, `ToDate`, `VillaId`, `UserId`.

### Process
1. `sp_delete_booking(@BookingId, @BookingRefNo, @User)` — soft or hard delete (SP-internal).
2. `ModifyVillaAvailability(... Status=70, Notes="Update status from Delete booking to available again")` to release the nights.

### Outputs / side effects
- **DB write:** booking row removed/marked; `VillaAvailability` rows flip 50 → 70.
- Public API gets a sync push to update the public site.

### Failure modes
- Partial sequence: if booking delete succeeds but availability flip fails, nights remain marked Booked even though booking row is gone. No retry visible.

### Open questions
- These two steps should be **one transaction** in the redesign — currently they're separate calls.
- "Available Again" (70) vs "Available" (10) — semantically the same; the legacy code distinguishes for audit (was-once-blocked). Decide whether to preserve.
