# Flywire Payment Gateway

Outbound calls to Flywire and inbound webhooks. The two outbound flows (`Charge` and `Pre-auth`) are currently `[DISABLED]` — only the **inbound webhook** is active, and it's **not signature-verified** `[SECURITY]`.

Cross-references:
- Outbound calls: `10-payment/payment-preauth.md` covers both disabled flows in detail.
- Inbound webhook: `10-payment/payment-collection.md` → `PAYMENT.COLLECTION.WEBHOOK_RECEIVE`.

## Gateway configuration

- **Base URL (hardcoded):** `https://api-platform-sandbox.flywire.com/` `[SECURITY]` — sandbox even in code marked "Production".
- **API key (hardcoded base64):** `S2EyL25NWnU5Ynl0T2lXSi91Q1pjdz09` in `ResService.cs:320, 384`.
- **Auth header:** `X-AUTHENTICATION-Key: {apiKey}` (varying case across call sites).

## Endpoints in use

| Endpoint | Direction | Status |
|---|---|---|
| `/payments/v1/payments/charge` | Outbound | `[DISABLED]` |
| `/commercial/v1/payment-requests` | Outbound | `[DISABLED]` |
| `/api/WordPressApi/Payment/PaymentStatusWebHook` (inbound to us) | Inbound | Active, **not verified** `[SECURITY]` |
| `/api/WordPressApi/Payment/TokenisePaymentStatus` (inbound from our public site) | Inbound | Active |

## Webhook → downstream cascade

When the inbound webhook reports `status=="guaranteed"`, the system fires:
1. `INTEGRATIONS.EMAIL.SEND` to payer + lead guest (receipt)
2. `INTEGRATIONS.ZOHO.PUSH_QUOTATION_BOOKING` with `Stage="Confirmed"`
3. `INTEGRATIONS.PUBLIC_API.PAYMENT_DUES_PUSH` to update WordPress
4. `SP_GET_SYNC_DATA_BY_MODULE(ResModule.FLYWIRE)` to mark sync done

If any of these fail, the webhook still returns 200 OK — the cascade is fire-and-forget.

## Open design questions for the Django redesign

- **Verify signatures**: HMAC-SHA256 over the raw body must be mandatory.
- **Idempotency**: webhook events must be deduped on `payment_id`.
- **Move credentials** to env / secret manager.
- **Re-enable or remove** the disabled outbound `Charge` and `Pre-auth` flows. Both have working data shapes; the redesign should revive them as typed Flywire calls with proper credential management (see `10-payment/payment-preauth.md`).

## Decided

- **Flywire is the payment gateway.** No multi-provider abstraction in v1. The `Payment.provider` enum stays extensible (`FLYWIRE`, `MANUAL_BANK_TRANSFER`) so a future second provider can be added without a migration, but no Stripe / other-gateway code paths are built.
