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
The booking modify path (`ResService.cs:3242-3250`) is **two sequential writes with no transaction wrapper**:
1. `ExecuteReadAsync(EDbQuery.SP_SAVE_BOOKING_INFO, param)` — persists the booking row and returns the new `bookingId` via the `@Id` output param.
2. Iff `bookingId > 0`, `ModifyVillaAvailability(new PropertyStatus { Action='UPDATE', FromDate, ToDate, QuotationNo, Status=50, Notes="Update from BookingModify by {UserId} : {User Email}", User, VillaId })` is called. This invokes SP `sp_villaAvailability`, which applies the delete-existing/insert-missing/update pattern, flipping status to 50 (Booked).

### Outputs / side effects
- **DB write:** `Booking` row (via `SP_SAVE_BOOKING_INFO`), then `VillaAvailability` rows in the range flip 40 → 50 (via `sp_villaAvailability`).
- Subsequent reads see the dates as Booked.

### Failure modes
- **Non-atomic two-write hazard** `[CORRECTNESS]` — the booking insert and the availability flip are two separate SP calls with no enclosing transaction. If the process dies (or the connection drops) between `SP_SAVE_BOOKING_INFO` and `sp_villaAvailability`, the booking exists but the dates do not transition to status 50 — they stay on whatever status the hold/prior state left them on. Subsequent searches still consider the property bookable; double-booking is then possible. The legacy code has **no compensation** for this.
- Race: if the hold has already auto-expired (status 70), the SP still works — it overwrites status 70 to 50.

### Django redesign requirement
- Wrap both writes in a single `transaction.atomic()` block, or — better — make the Booking save the **only** authoritative write, and derive availability from `Booking` / `BookingHold` ranges through Postgres `EXCLUDE` constraints on `daterange`. The `VillaAvailability` daily grid is a legacy artefact that should disappear in the redesign (see `09-departures.md` row for `VillaAvailability`).

---

## Booked → Available on booking cancellation

**ID:** `AVAILABILITY.TRANSITION.BOOKED_TO_AVAILABLE`
**Trigger:** Booking deletion / cancellation (see `09-booking/booking-cancellation.md`).
**Actor:** System.
**Legacy locus:** `ResService.cs:913-931` (`DeleteBooking`).

### Inputs
- `BookingId`, `QuotationNo`, `FromDate`, `ToDate`, `VillaId`, `UserId`.

### Process
The deletion path (`ResService.cs:913-931`) is **two sequential writes with no transaction wrapper**:
1. `ExecuteCreateAsync("sp_delete_booking", ref param)` with `@BookingId`, `@BookingRefNo`, `@User` — soft or hard delete (SP-internal).
2. `ModifyVillaAvailability(PropertyStatus { ... Status=70, Notes="Update status from Delete booking to available again" })` to release the nights.

### Outputs / side effects
- **DB write:** booking row removed/marked; `VillaAvailability` rows flip 50 → 70.
- Public API gets a sync push to update the public site.

### Failure modes
- **Non-atomic two-write hazard** `[CORRECTNESS]` — same shape as `HOLD_TO_BOOKED` above. If `sp_delete_booking` succeeds but `sp_villaAvailability` fails (network, lock, deadlock, process crash), the booking row is gone but the daily-grid rows stay at status 50 (Booked). The villa is then "booked" against a booking that doesn't exist — manual cleanup is the only recovery, and the `catch(Exception ex)` block at line 927-930 swallows the failure and returns `false` with no telemetry beyond the lost logger call.

### Django redesign requirement
- Wrap both writes in `transaction.atomic()`, or eliminate the daily-grid mirror entirely (see redesign note in `HOLD_TO_BOOKED` above).
- Replace the silent `return false` on exception with a typed result + structured log; this is a `[CORRECTNESS]` issue, not just a code-quality one.

### Open questions
- "Available Again" (70) vs "Available" (10) — semantically the same; the legacy code distinguishes for audit (was-once-blocked). Decide whether to preserve.
