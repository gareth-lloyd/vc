# 10 · Payment

Money in and money out. The legacy system uses **Flywire** as the payment gateway (sandbox URL hardcoded in source — `[SECURITY]` `[DISABLED]` for production). Three actions matter:

- **Inbound webhook** from Flywire reports a payment status change
- **Tokenized-payment record** captured when a guest completes the gateway flow
- **Manual payment record** (bank transfer) entered by staff

Plus the checkout-form flow (capture guest personal info before payment) and the disabled pre-authorisation flow (security deposit hold).

## Files

| File | Workflows |
|---|---|
| [`payment-collection.md`](./payment-collection.md) | Tokenized payment status save, payment webhook receipt, manual payment record |
| [`checkout-flow.md`](./checkout-flow.md) | Save checkout personal info, confirm/reject booking from gateway page, push payment-dues schedule to WordPress on success |
| [`payment-preauth.md`](./payment-preauth.md) | Pre-authorisation for security deposit hold (entire workflow `[DISABLED]`), tokenized recurring charge (`[DISABLED]`) |

## Entities touched

- `VillaPaymentStatus` — record of received payments, written by webhook and by manual flows. Columns: `PaymentReferenceNo`, `Status`, `Amount`, `PayerAmount`, `AmountCurrency`, `PayerAmountCurrency`, `PaymentMethod`, `BookingReferenceNo`, `BookingId`, `VillaId`, `CreatedAt`, `CreatedBy`, plus tokenization fields (`Token`, `PaymentType`, `ReferenceId`, `Sig`)
- `VillaPaymentDetail` — internal payment-detail rows (written from within SPs)
- `CheckoutPersonalInfo` / `CheckoutAdditionalInfo` — guest details captured at checkout
- `VillaCheckoutDetail` — checkout flow tracking (PaymentId for pre-auth installments)
- `VillaAvailability` — updated to status 60 (on-hold pending confirmation) after a payment record

## Stored procedures

- `sp_addPaymentDetails` (a.k.a. `SP_ADD_PAYMENT_DETAILS`) — write payment status row
- `sp_save_payment_info` — webhook-driven write (different parameter shape)
- `sp_checkout_personal_info`, `sp_checkout_additional_info` — checkout form persistence
- `SP_CONFIRM_BOOKING` — reused for confirm/reject from the gateway page
- `SP_CHECKOUT_DETAILS` — checkout milestone tracking

## Cross-cutting notes

- **Currency convention**: Flywire reports amounts in cents/pence as strings; internal storage divides by `Constant.GBP_BILLING_CENT = 100`. Multi-currency receipts are captured (`AmountCurrency` + `PayerAmountCurrency`) but internal billing uses GBP.
- **No webhook signature verification** `[SECURITY]` — the `Digest()` method exists in `PaymentController` but is never called. Any attacker who learns the URL can forge payment confirmations.
- **No idempotency** `[SECURITY]` — duplicate webhooks create duplicate `VillaPaymentStatus` rows.
- **Tokens stored plaintext** `[SECURITY]` — `Token`, `Sig`, `Reference` saved as-is.
- **Hardcoded credentials** in source:
  - Flywire API key `S2EyL25NWnU5Ynl0T2lXSi91Q1pjdz09` (base64) in `ResService.cs:320, 384`
  - Internal API key `130d0022-8fe4-4878-8ec2-c44c939bb336` in `PaymentController` constructor
- **Sandbox URL hardcoded** as production endpoint: `https://api-platform-sandbox.flywire.com/`.
