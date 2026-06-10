# FG-012 — Track-payments POST creates ledger rows straight from `request.data`

- **Severity:** 🟠 Footgun
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `payments/views/track.py:273–291`

## Problem

`_track_payments` POST builds a `Payment` directly from the raw request body
— no serializer, no service, no idempotency:

```python
payment = Payment.objects.create(
    booking=booking,
    purpose=purpose,
    status=data.get("status", PaymentStatus.PENDING.value),
    amount=_parse_decimal(data.get("amount", 0)),
    ...
)
```

Consequences:

- A client-supplied `status` can mint a `SUCCEEDED` row without going
  through `transition_to` — no `payment_succeeded` signal, so the booking
  never advances and no PaymentEvent/audit trail of the settlement exists.
- An unvalidated `amount` (`"abc"`) makes `_parse_decimal` raise
  `decimal.InvalidOperation` → 500.
- Operator double-click creates duplicate rows (no `idempotency_key`),
  racing the active-per-purpose constraints.

## Proposed fix

Route through a write serializer + service per the layering convention:
serializer validates amount/method/due_at and rejects (or whitelists)
client-supplied `status`; the service creates the row PENDING and uses
`Payment.mark_paid` for recorded manual receipts so signals and events fire;
accept an optional `idempotency_key` via `core.idempotency`.

## Acceptance

- API tests: posting `status=SUCCEEDED` either 400s or lands via
  `mark_paid` (signals fired, booking advanced); garbage `amount` → 400 not
  500; a retried POST with the same idempotency key returns the original
  row.

## Dependencies

Related: SMELL-008 (service-layer contract backfill — this is the worst
offender), BUG-011 (same file's error handling).
