# Quotation Lifecycle

State transitions on a quotation: accept → booking, lose, expire.

## Convert quote to booking

**ID:** `QUOTATION.LIFECYCLE.CONVERT_TO_BOOKING`
**Trigger:** Either client clicks "Accept" link in the emailed quote OR staff manually confirms after verbal acceptance.
**Actor:** Guest (via emailed link) or staff.
**Legacy locus:** The handler is on the booking side — see `09-booking/booking-creation.md` → `BOOKING.LIFECYCLE.CREATE_FROM_QUOTATION`.

### Inputs (from quote-side perspective)
- `QuotationId`
- Any client-side details captured at acceptance time (payer info, billing address)

### Process (quote-side)
1. Locate quote master; gather line items + client.
2. Hand off to the booking workflow (which creates the `VillaBooking` row and the 3-tier `VillaPayment` schedule, updates availability to status 50, sends emails, pushes to Zoho).
3. Quote `Stage` updates to `Accepted`.

### Outputs / side effects (from quote-side)
- **DB write:** `VillaQuotationMaster.Stage = Accepted` (implied; see booking workflow for full detail).

### Open questions
- "Client-clickable acceptance URL" implementation is not in committed code; flow is staff-driven. Decide whether the redesign exposes a true self-service accept flow (with token + secure URL).

---

## Mark quote lost

**ID:** `QUOTATION.LIFECYCLE.MARK_LOST`
**Trigger:** Staff action (no committed UI captured; inferred from `ZohoQuoteStage.Lost` enum).
**Actor:** Staff.

### Inputs
- `QuotationId`, optional reason

### Process (inferred)
1. Update `VillaQuotationMaster.Stage = "Lost"`.
2. Push to Zoho.

### Outputs / side effects
- **DB write.**
- **Zoho push.**

### Open questions
- The lost-reason field and explicit transition workflow should be added in the redesign.

---

## Expire quote

**ID:** `QUOTATION.LIFECYCLE.EXPIRE`
**Trigger:** Not implemented as a scheduler.
**Status:** `[STUB]` — there is no time-based quote expiry. The only related expiry is the **7-day hold** in availability.

### Open questions
- Add deterministic quote-level expiry in the redesign (e.g., `valid_until` populated at send-time = `ToDate.AddDays(6)`; a scheduled sweep marks expired quotes accordingly and releases linked holds).
