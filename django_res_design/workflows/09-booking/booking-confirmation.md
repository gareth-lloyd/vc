# Booking Confirmation (Owner Approval)

Villa Collective bookings require **owner approval** — the property owner confirms or rejects each booking. This workflow records the decision and notifies the guest.

## Confirm or reject booking

**ID:** `BOOKING.LIFECYCLE.OWNER_CONFIRM`
**Trigger:** Owner replies to confirmation email and staff updates the system, OR staff "Confirm on behalf" action, OR direct API call.
**Actor:** Staff (on behalf of owner) or owner (external trigger; current code is staff-driven).
**Legacy locus:** `ResService.cs:4536-4594` (`ConfirmBooking`); `PaymentController.cs:204-233`; SP `SP_CONFIRM_BOOKING`.

### Inputs
`BookingConfirmationArgs`:
- `BookingId` (`bookingId`, required > 0)
- `BookingRef` (e.g., `"VC12345"`)
- `IsConfirm` (bool — true = approve, false = reject)
- `Reason` (required when `IsConfirm = false`)

### Process
1. **Controller validates**: `bookingId > 0`; if rejecting, `reason` non-blank (`PaymentController.cs:212-225`).
2. **Look up guest email** via:
   ```sql
   SELECT VC.Email, VB.Id BookingId FROM VillaBooking VB
   LEFT JOIN VillaQuotationMaster QM ON VB.QuotationNo = QM.QuotationNo
   LEFT JOIN VillaClientDetails VC ON QM.ClientDetailsId = VC.Id
   WHERE VB.Id = {args.BookingId}
   ```
   (`ResService.cs:4541-4549`) — raw concatenated SQL, mitigated only by int parsing.
3. `SP_CONFIRM_BOOKING` with `@BookingId`, `@IsConfirmBooking`, `@Reason`.
4. **Send email to guest**:
   - `Module = "Enquiry_Email"`
   - `Subject = "For Villa booking confirmation"`
   - `Body =` rejection reason if rejected, else empty
   - `EmailService.SentEmail(emailConfig)`

### Outputs / side effects
- **DB write:** `VillaBooking.IsOwnerConfirmed` flipped (true/false). Probably also writes a status timestamp; SP body not in committed source.
- **Email out:** to guest.
- **Booking UI**: button colour transitions to "Owner Confirmed" state (`Booking.razor:37, 510-514`).
- **No event row** for the transition.

### Failure modes
- Booking not found → error message returned in `Response.Data`; controller still returns 200 OK.
- Email send fails → exception caught, not surfaced to caller; guest may not be notified.

### Open questions
- The legacy flow assumes staff manually transcribes the owner's reply. The Django redesign could offer a self-service token-based "approve / reject" page emailed directly to the owner.
- "Rejected" status is one-shot — there's no re-confirm path captured. Decide if rejection is terminal.
- Add a `BookingEvent` audit row (transition, actor, reason, timestamp).
