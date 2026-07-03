# Booking Cancellation

Removing a booking and releasing its availability. The legacy implementation is admin-only and unconditional — there is no refund-on-cancel logic.

## Cancel / delete booking

**ID:** `BOOKING.LIFECYCLE.CANCEL`
**Trigger:** Trash icon on a booking row in `BookingInfo.razor:156` (admin-only — gated by `IsSystemAdmin`).
**Actor:** System administrator.
**Legacy locus:** `ResService.cs:913-931` (`DeleteBooking`); SP `sp_delete_booking`.

### Inputs
- `BookingSummery` (the booking summary object — gives `QuotationNo`, `FromDate`, `ToDate`, `VillaId`)
- `UserId` (admin)

### Process
1. `sp_delete_booking @BookingId, @BookingRefNo, @User` — soft- or hard-delete (SP body not in committed source; assume soft based on the project's overall pattern).
2. **Release availability**: `ModifyVillaAvailability(..., Status=70, Notes="Update status from Delete booking to available again")` → `AVAILABILITY.TRANSITION.BOOKED_TO_AVAILABLE`.
3. Refresh booking list UI; toast "Booking deleted successfully".

### Outputs / side effects
- **DB write:** booking marked deleted (or removed); `VillaAvailability` range flips 50 → 70.
- **No payment refunds** triggered.
- **No Zoho update** triggered.
- **No emails** sent.

### Failure modes
- Booking has paid payments → no check; silently proceeds.
- Booking not found → exception caught, silent.
- Availability flip fails after booking delete → calendar shows dates still booked even though booking row is gone.

### Open questions
- The current flow is a "data delete" not a "business cancellation". Django redesign should:
  - Add a `BookingCancellation` workflow with reason, fee, refund decision.
  - Trigger refund payments through the payment workflow (currently no API for that — see `10-payment/`).
  - Update Zoho stage to `Cancelled`.
  - Email the guest and the owner.
  - Write a `BookingEvent` audit row.
