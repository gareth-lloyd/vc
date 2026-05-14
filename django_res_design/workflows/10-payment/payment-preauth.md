# Payment Pre-Authorisation `[DISABLED]`

Two payment-gateway workflows that exist as committed but **commented-out** code. Documented for completeness and for the Django redesign to decide whether to revive.

## Pre-authorise security deposit hold

**ID:** `PAYMENT.PREAUTH.SECURITY_DEPOSIT` `[DISABLED]`
**Trigger:** Would fire during guest checkout to authorise (but not capture) the security deposit amount.
**Actor:** Guest, Flywire.
**Legacy locus:** `ResService.cs:348-468` — **entire method commented out**.

### Inputs (had it been wired)
`PreAuthPayReqDTO`:
- `recipient`: `{ id: "VCO", fields: [{ id: "invoice_id", value: bookingRefNo }, { id: "invoice_detail_id", value: invoiceDetailsId }] }`
- `sender` (payer): `firstName`, `lastName`, `email`, `phone`, `address` (`street1`/`street2`/`city`/`state`/`country`/`postalCode`)
- `installments`: `[{ serviceDescription: "Security Deposit pre auth payment", amount: amount × 100 }]` (cents)
- `expirationDate` (ISO)
- `createOptions`: `{ requireSavePaymentMethod: true, preAuth: true, sendCreateEmail: false }`

### Process (had it been wired)
1. Query `VW_VillaEnquireDetail` for the booking → extract sender + address.
2. **Production guard**: only run if environment == Production. (Current code still hardcodes the sandbox URL even in production — `[SECURITY]` mistake.)
3. POST to `https://api-platform-sandbox.flywire.com/commercial/v1/payment-requests` with header `X-Authentication-Key: {key}`.
4. Response `PreAuthResponseVM` carries `Status="ACTIVE"` and `Installments[]`.
5. Persist installment id via `SP_CHECKOUT_DETAILS @Description=SECURITY_DEPOSIT, @PaymentId=installmentId`.

### Outputs / side effects (had it been wired)
- Pre-auth hold placed on the guest's card.
- `VillaCheckoutDetail` row with the installment id.
- Pre-auth expires automatically at `expirationDate` if not captured.

### Failure modes
- Hardcoded credentials and sandbox URL `[SECURITY]`.
- No retry / DLQ.
- Silent failure path (`isSuccess=false`) — guest doesn't know.

### Open questions
- The pre-auth idea is sound: hold the security-deposit amount without charging until departure inspection. The Django redesign revives it as a typed Flywire integration with proper credential management (env / secret manager, not source).

---

## Tokenized recurring charge `[DISABLED]`

**ID:** `PAYMENT.PREAUTH.RECURRING_CHARGE` `[DISABLED]`
**Trigger:** Would fire from the scheduler when a future payment (typically rental balance) comes due.
**Actor:** System.
**Legacy locus:** `ResService.cs:295-346` (`InvokeChargeApi`) — commented out at the caller site (`ResService.cs:204-207`).

### Inputs (had it been wired)
- `token` (stored tokenized payment method from a previous tokenization)
- `args.BookingNo`, `args.Id` (checkout detail id)
- `amount` (decimal; converted to cents)

### Process (had it been wired)
1. Environment guard.
2. Build `PaymentChargeRequest`:
   ```
   {
     charge_intent: { mode: "subscription" },
     payment_method_token: token,
     recipient: { id: "VCO", fields: [
       { id: "invoice_id", value: "VC{bookingNo}" },
       { id: "invoice_detail_id", value: checkoutDetailId }
     ] },
     items: [{ id: "default", amount: amount × 100 }],
     external_reference: "Rental balance Payment"
   }
   ```
3. POST to `https://api-platform-sandbox.flywire.com/payments/v1/payments/charge` with `X-AUTHENTICATION-Key`.
4. Response `PaymentChargeResponse` with `payment_reference`, `charge_info`, `charge_result.status` ∈ {success, pending, failed}, `payer`.
5. Persist reference via `sp_updateZohoId`.

### Outputs / side effects
- Charge attempted; reference stored.
- Logs request/response to file.

### Failure modes
- No retry on network failure.
- No idempotency key in the request.
- Hardcoded credentials.

### Open questions
- The scheduler currently sends a *reminder email* instead of charging (because this code is disabled). Decide for the redesign whether automated charging is desired (with explicit guest consent) or whether the reminder flow stays.
