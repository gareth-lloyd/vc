# Booking Creation

The "Start Booking" workflow that materialises a confirmed booking from a quotation. This is one of the largest workflows in the legacy system — it touches DB, availability, Zoho, WordPress, and email.

## Create booking from quotation

**ID:** `BOOKING.LIFECYCLE.CREATE_FROM_QUOTATION`
**Trigger:** "Start/Update Booking" or "Start Booking - No Send" button on `Pages/Bookings/Booking.razor` (lines 462, 471).
**Actor:** Staff.
**Legacy locus:** `Booking.razor:720-762, 886-924`; `ResService.cs:3194-3397` (`ModifyBookingDetails` / save path); many SPs.

### Inputs
`ResBookingDetails` (BookingInfoModels.cs:70-219):

Reservation:
- `QuotationNo`, `FromDate`, `ToDate`, `VillaId`
- `Adult`, `Children`, `IsTBC`

Pricing:
- `RentalPrice`, `CurrencyId`
- `IsOverrideDeposit`, `OverrideDeposit` (deposit % override)
- `IsSecDepAmt`, `SecurityAmount` (security deposit override)
- `IsDiscount`, `DisclountValue` `[TYPO]`, `IsAdjustment`, `AdjustmentValue`
- `BalanceDue`, `BalanceDueDate`

Concierge:
- `ConciergeService` (`1`/`2`), `ConciergeId`, `ConciergePrice`

Payment:
- `PaymentMethod` (`10`=CC, `20`=BT)
- `PaymentDetails[]` — three rows for the 3-tier schedule (computed in step 2)

Parties:
- `ClientDetails` — guest info
- `PayerDetails` — if different from guest
- `AgentDetails` — agent / broker

Content:
- `Notes`, `InteralNotes` `[TYPO]`, `HouseRules`, `TagsInformation`

Optional:
- `VillaOwnerDetails` — when the "Start Booking" variant is clicked (vs "No Send"), used to send the owner's confirmation email

### Process

1. **Validate**: `sp_check_availability` for the requested range (excluding this booking's id on update), reject any payment already recorded, ensure user session still valid, at least one adult/child or `IsTBC` checked, balance due date < arrival date.

2. **Compute payment breakdown** (`Booking.razor:720-762`):
   - `adjustedAmount = RentalPrice + Adjustment - Discount`
   - **Initial Deposit** = `CalcInterest(adjustedAmount, OverrideDeposit %)` (or override fixed value)
   - **Rental Balance** = `adjustedAmount - InitialDeposit + ConciergePrice`
   - **Security Deposit** = `CalcInterest(RentalPrice, SecurityDepositAmount, type)` — `type` is `1=%` or `2=fixed`
   - **Full-payment short-circuit**: if days-to-arrival < `BalanceDue`, zero the deposit, push balance due to today+2.
   - Populate `PaymentDetails[]` with `Description`, `Amount`, `Date`, `PaymentMethod`.

3. **Save booking row** — `SP_SAVE_BOOKING_INFO` with the constructed parameters (`CreateParams(args)`). Output `@Id` returns the booking id.

4. **Save payment schedule** — for each `PaymentDetails` row: `SP_GET_PAYMENTDETAILS` (INSERT or UPDATE keyed by row id).

5. **Update availability** — `ModifyVillaAvailability(... Status=50, Notes="Update from BookingModify by {UserId} : {User Email}")`. This is `AVAILABILITY.TRANSITION.HOLD_TO_BOOKED` (see `06-availability/booking-status-transitions.md`).

6. **Generate WordPress checkout URL** (`ResService.cs:3320-3355`):
   - Build checkout payload with personal info, payment schedule, villa details.
   - `_apiService.PushVillaBookingToWP(payload)` → POST to `{site}/Import_Booking`.
   - Persist the returned URL: `UPDATE VillaBooking SET BookingUrl='{url}' WHERE Id={id}` `[SECURITY]` raw SQL.

7. **Send guest email** — `SentEmailAsync(EmailTemplate.INITIAL_PAYMENT_TEMPLATE, QuotationNo)` (renders via `SP_GET_EMAIL_TEMPLATE_DATA`, sends via `EmailService`).

8. **Send owner email** (when not the "No Send" variant and owner provided) — `SentEmailToOwner(QuotationNo)`; logs template via `SP_SAVE_VC_EMAIL_TEMPLATE` with `Type=CC_VO_BOOKING_CONFIRMATION`.

9. **Push to Zoho** — background `PushZohoBooking(model, "Booked")` → `INTEGRATIONS.ZOHO.PUSH_QUOTATION_BOOKING` with module `VILLA_BOOKING`.

### Outputs / side effects

- **DB writes:** `VillaBooking` (new or updated row), `VillaPayment` (3 rows minimum), `VillaAvailability` (range flipped to status 50), `VillaClientDetails` (guest fields).
- **State transitions:**
  - Booking → "Underway" (button colour change at `Booking.razor:36`)
  - Availability → status 50 (Booked)
- **Emails out:** guest (`INITIAL_PAYMENT_TEMPLATE`); owner (`CC_BOOKING_CONFIRM` template logged via SP).
- **WordPress:** booking imported, checkout URL returned and stored.
- **Zoho:** record in `VILLA_BOOKING` module.

### Data transformations for storage

- `BookingRef = "VC" + QuotationNo` for display; SP boundaries strip the prefix.
- Initial deposit %: `OverrideDeposit` (10%–80%, 10% increments) or system default.
- Discount and Adjustment apply *before* deposit calculation.
- Concierge included only when `ConciergeService == 2` (Signature tier).
- Status enum mappings:
  - `InitialPaymentStatus.AWAITING_DEPOSIT`
  - `BalancePaymentStatus.BALANCE_DUE`
  - `DepsitPaymentStatus.AWAITING_SD_DETAILS` `[TYPO]`

### Failure modes

- Quotation number invalid → abort.
- Dates unavailable → "Selected booking date already booked for another user".
- Session expired → "Session expired. Please log in again".
- Payment already recorded → "Modification is not allowed after initial payment completed".
- WordPress checkout link generation fails → toast error; booking saved but no checkout URL.
- Zoho push fails (async, non-blocking) → log only.

### Open questions

- The order of operations is risky: DB writes happen *before* the WordPress/Zoho/email steps and there's no rollback if any of those fail.
- The "Full payment short-circuit" math should be wrapped in a dedicated `PaymentScheduleBuilder` service.
- `[TYPO]` to fix in models: `InteralNotes`, `DisclountValue`, `DepsitPaymentStatus`.
