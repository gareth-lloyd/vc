# Booking Management

Read-side workflows on bookings.

## List bookings

**ID:** `BOOKING.MGMT.LIST`
**Trigger:** Navigate to `/booking-info` (`Pages/Bookings/BookingInfo.razor`).
**Actor:** Staff.
**Legacy locus:** `BookingInfo.razor:240-246`; `ResService.cs:4217-4238` (`GetBookingData`); SP `SP_GET_BOOKING_DETAILS`.

### Inputs
`PageEventArgs`: `Skip`, `Take`, `SearchText`, `Column` (sort field), `SortOrder`.

### Process
1. Execute SP with pagination + search.
2. Returns `List<BookingSummery>` `[TYPO]`.

### Outputs / side effects
- Grid columns: VC Ref (`BOOK_REF` prefix + `QuotationNo`), Client Name, From/To, Enq/Quote Date, Person (CreatedBy), Deposit status, Balance status, Sec Dep status.
- Status badges (`InitialPayment` / `RentalBalancePayment` / `SecurityDeposit` strings) colour-code (green if "paid", dark otherwise).

---

## View booking detail

**ID:** `BOOKING.MGMT.VIEW_DETAIL`
**Trigger:** Click a booking row, or navigate to `/booking-info/{QuotationNo}/{Id}`.
**Actor:** Staff.
**Legacy locus:** `Booking.razor:574-610`; `ResService.cs:3803-3850+` (`GetBookingDetailsByRef`); SP `SP_GETBOOKINGDETAILSBYID`.

### Process
1. Hydrate `ResBookingDetails` from SP (multi-result-set: booking + payments + concierge + notes).
2. Lookup owner details via `VillaId`.
3. Load currency symbols for every quoted currency.
4. Load concierge service levels and prices.
5. Load existing payment records.
6. Render six panels:
   - Customer details, Payer details, Customer notes
   - Booking details (dates, party size, rental, notes)
   - Owner details (read-only)
   - Villa details (inclusion, house rules)
   - Finance details (3-tier schedule, possibly editable if not paid)
   - Concierge details (optional service level + add-ons)
7. Initialise rich-text editors (contenteditable divs) for the various notes panels.

### Outputs / side effects
- Read-only; UI only.

---

## Resend booking summary / receipt

**ID:** `BOOKING.MGMT.RESEND_RECEIPT`
**Trigger:** "Resend Booking Summary" button on a booking row (`BookingInfo.razor:155`).
**Actor:** Staff.
**Legacy locus:** `BookingInfo.razor:208`; `ResService.cs:5031-5051` (`SentReceiptEMailAsync`); SP `SP_GET_EMAIL_TEMPLATE_DATA`.

### Inputs
- `QuotationNo` (parsed from the display reference: strip `VC` prefix).

### Process
1. Strip `VC` prefix; parse remainder to int.
2. `SentReceiptEMailAsync(EmailTemplate.BOOKING_RECEIPT, bookingNo)`.
3. Template fetched via SP, rendered with placeholders (guest name, dates, payments, etc.).
4. `EmailService.SentEmail()`.

### Outputs / side effects
- **Email out:** booking receipt to guest.
- Toast "Receipt Sent successfully to {client name}".

### Failure modes
- Missing guest email → send fails.
- Template not found → exception.
