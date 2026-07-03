# Payment Collection

The three paths by which a payment gets recorded into `VillaPaymentStatus`: the tokenization callback after a guest completes the gateway flow, the inbound Flywire webhook, and the staff "manual record" entry.

## Save tokenized-payment status

**ID:** `PAYMENT.COLLECTION.SAVE_TOKEN_STATUS`
**Trigger:** Frontend `POST /api/WordPressApi/Payment/TokenisePaymentStatus` after Flywire returns the guest to the site.
**Actor:** Guest (unauthenticated), system.
**Legacy locus:** `ResService.cs:4309-4372` (`AddPaymentDetails`); SP `sp_addPaymentDetails`.

### Inputs
`TokenizePaymentResponse`:
- `amount` (decimal), `amountCurrency` (originally quoted currency)
- `payerAmount`, `payerAmountCurrency`
- `reference` (string — Flywire transaction id)
- `token` (string — tokenized method id from Flywire)
- `status` ("guaranteed" / "processing" / etc.)
- `bookingId`, `bookingRefNo` (`"VC..."`), `villaId`
- `sig` (webhook signature — captured, **not verified** `[SECURITY]`)
- `type` (payment type), `paymentMethod`, `brand`, `digits`, `expirationMonth`, `expirationYear`

### Process
1. Parse `bookingRefNo` via `GetBookingNo()` lambda — strips `VC` prefix.
2. Build parameter list (`@BookingRefNo`, `@BookingId`, `@VillaId`, `@PaymentRefNo`, `@Status`, `@Amount`, `@PayerAmount`, `@AmountCurrency`, `@PayerAmountCurrency`, `@PaymentMethod`, `@PaymentType`, `@ReferenceId`, `@Token`, `@Sig`).
3. Execute `sp_addPaymentDetails`.
4. Log all parameters to file `payment_callback_database`.

### Outputs / side effects
- **DB write:** `VillaPaymentStatus` row inserted; SP cascades to `VillaPaymentDetail`.
- **Return:** `Response { Status=true, Message="Payment details saved successfully..." }`.

### Data transformations for storage
- No currency conversion (gateway has already done it).
- Token stored plaintext `[SECURITY]`.

### Failure modes
- Bad `bookingRefNo` format → `GetBookingNo` returns 0; SP write proceeds with zero ref.
- **No idempotency** `[SECURITY]` — duplicate POSTs create duplicate rows.

### Open questions
- Add idempotency on `(reference, booking_id)`.
- Encrypt tokens at rest or stop storing them.

---

## Receive payment webhook (Flywire)

**ID:** `PAYMENT.COLLECTION.WEBHOOK_RECEIVE`
**Trigger:** Flywire POST to `/api/WordPressApi/Payment/PaymentStatusWebHook`.
**Actor:** Flywire (external).
**Legacy locus:** `PaymentController.cs:98-143`; `ResService.PaymentStatusNotification`; SP `sp_save_payment_info`.

### Inputs
JSON body deserialized to `WebhookPayload`:
- `event_type`, `event_date`, `event_resource`
- `data` (deep object):
  - `payment_id`, `amount_from`, `currency_from`, `amount_to`, `currency_to`, `status`, `expiration_date`, `external_reference`, `country`
  - `payment_method` (nested: `type`, `brand`, `card_classification`, `card_expiration`, `last_four_digits`)
  - `fields` (nested: `invoice_id`=`"VC{ref}"`, `invoice_detail_id`)
  - `payer` (full nested address)
  - `payouts` (array)
  - `reversed_type`, `reversed_amount`, `reason`, `reason_code`, `client_reason`, `cancellation_reason`, `recurring_id`

### Process
1. `Request.EnableBuffering()`; read raw body (for HMAC verification — but **`Digest()` is defined and never invoked**) `[SECURITY]`.
2. Reset stream, JSON-deserialize.
3. Log full payload to file `payment_status_webHook_params`.
4. **No signature check.**
5. `ResService.PaymentStatusNotification(data)`:
   - SP `sp_save_payment_info` with `@BookingRefNo`, `@Amt` (= `amount_to / 100`), `@PayerAmt` (= `amount_from / 100`), `@PayerCurrency`, `@InvoiceDetailId`, `@Status`, `@PaymentId`, `@Country`, `@PaymentMethod`.
   - Log to `payment_status_notification_database`.
6. **If `status == "guaranteed"`** (success):
   - `SentEmailToPayerAndLeadGuest(bookingRefNo)` — receipts.
   - Look up booking, `PushZohoBooking(details, "Confirmed")`.
   - `GetCheckoutDetails(bookingRefNo)` → push the remaining `PaymentDuesDates` to WordPress via `PushCheckOutDataToWP` (see `11-integrations/public-website-sync.md`).
   - `SP_GET_SYNC_DATA_BY_MODULE(ResModule.FLYWIRE)` to mark synced.

### Outputs / side effects
- **DB write:** `VillaPaymentStatus` row.
- **Email out:** receipts to payer + lead guest.
- **WordPress push:** updated payment schedule.
- **Zoho push:** booking stage = `Confirmed`.

### Data transformations for storage
- Cents → pounds: `amount_to / 100` using `Constant.GBP_BILLING_CENT = 100`.
- Status string-compared exact: `"guaranteed".IsEqual(args.Status.Trim())`.

### Failure modes
- **No signature verification** — forgeable.
- **No idempotency** — replays produce duplicates.
- Email send failure does not roll back the DB write — partial states possible.
- Missing `fields.invoice_id` → `GetBookingNo` returns 0; row written with booking ref `0`.

### Open questions
- HMAC-SHA256 verification (the `Digest()` method) MUST be wired in.
- Add a `webhook_deliveries` table with idempotency on `(provider, event_id)`.
- Wrap the post-success cascade in retryable Celery tasks; webhook handler should return 200 OK immediately.

---

## Record manual payment (staff)

**ID:** `PAYMENT.COLLECTION.RECORD_MANUAL`
**Trigger:** Staff/admin POST to `/api/WordPressApi/Payment/PaymentStatus` with `PaymentStatusArgs`.
**Actor:** Staff (used for bank transfers, cheques, wires — anything that didn't go through Flywire).
**Legacy locus:** `PaymentController.cs:44-94`.

### Inputs
`PaymentStatusArgs`:
- `payRefNo` (manually-generated reference, e.g. `"BANK-TRANSFER-001"`)
- `status` (e.g., `"completed"`)
- `amount`, `payerAmount`, `amountCurrency`, `payerAmountCurrency`
- `paymentMethod` (e.g., `"bank_transfer"`, `"wire"`, `"check"`)
- `bookingRefNo`, `bookingId`, `villaId`
- `confirmBookingLink` (unused), `signature` (unused for manual), `type`, `token`, `isConfirmed`, `rejectionText`

### Process
1. Validate: `payRefNo`, `status`, `villaId>0`, `bookingId>0`, `bookingRefNo` non-blank.
2. Wrap into `PaymentCallbackArgs`:
   ```
   { custom_fields = { invoice_id = BookingRefNo }, payment_id = PayRefNo, status, payment_request_type = PaymentMethod }
   ```
3. Log to file `payment_payment_status`.
4. `_service.AddPaymentDetails(data)` (same `sp_addPaymentDetails` path as tokenized).
5. `_service.UpdateAvailabilty(args.BookingId, 60, "Update from the AddPaymentStatus from payment controller")` — flips availability to status 60 (on-hold pending confirmation).
6. Return 200 OK.

### Outputs / side effects
- **DB write:** `VillaPaymentStatus`, plus `VillaAvailability` flip to 60.
- **No emails**, **no Zoho update**.

### Failure modes
- Validation rejection → 200 OK with error message in `res.Data`.
- Duplicate POST → duplicate rows.
- Manual entries indistinguishable from webhook entries in the DB → no audit trail of source `[AUDIT]`.

### Open questions
- Differentiate "source" on the payment row (`webhook` / `manual` / `tokenized`).
- Require evidence (file upload) for manual entries.
