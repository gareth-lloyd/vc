# Booking Modification

Updating dates, party size, pricing, payment method, or concierge on an existing booking. Re-runs most of the booking-creation pipeline.

## Modify booking

**ID:** `BOOKING.LIFECYCLE.MODIFY`
**Trigger:** Edit on the booking page; same "Start/Update Booking" button used.
**Actor:** Staff.
**Legacy locus:** Same path as `CREATE_FROM_QUOTATION`; `ResService.cs:3194-3260, 3320-3355`.

### Inputs
Modified `ResBookingDetails` with updated:
- Dates, party size, price, discount/adjustment, concierge level
- Payment method, payment dates
- Notes, preferences
- Security deposit override
- Optional `VillaOwnerDetails` (when sending owner email)

### Process
1. **Validation gates** (`Booking.razor:886-914`):
   - Owner email present (if sending).
   - Balance due date < arrival date.
   - `IsDepositePaid != true` — initial payment must not already be completed.
   - User session valid.
   - Adults + Children > 0 or `IsTBC` set.
2. **Recompute 3-tier breakdown** (`Booking.razor:720-762`) — same math as booking creation.
3. **Update booking row**: `SP_SAVE_BOOKING_INFO` (UPSERT keyed by id).
4. **Update payment schedule**: for each `PaymentDetails`, `SP_GET_PAYMENTDETAILS` (INSERT/UPDATE/DELETE). Deletes happen for items marked with `DbAction.DELETE` in the in-memory list.
5. **Update availability** (only if dates changed): `ModifyVillaAvailability` to re-pin the new range.
6. **Refresh WordPress checkout URL**: `PushVillaBookingToWP` with new payload.
7. **Conditional emails**: `INITIAL_PAYMENT_TEMPLATE` to guest, owner confirmation template logged for owner (only on the "Start/Update Booking" variant, not "No Send").
8. **Zoho push** (async): `PushZohoBooking(model, "Booked")`.

### Outputs / side effects
- Same as creation: updated DB rows, possibly availability range shifted, new checkout URL stored, optionally new emails dispatched, Zoho updated.

### Failure modes
- Balance due ≥ arrival date → blocked.
- Initial deposit already paid → "Modification is not allowed after initial payment completed".
- Date conflict on new range → "Selected booking date already booked".

### Open questions
- **Date-change with paid deposit** is hard-blocked. Decide whether the redesign allows date-change with paid deposit + a refund flow.
- The "delete payment line" path (`PaymentDetails` row with `Action=DELETE`) is fragile — a paid payment line shouldn't be deletable.
