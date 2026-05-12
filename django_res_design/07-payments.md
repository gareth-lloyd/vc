# 07 — Payments

Separate app — webhook surface and audit boundary justify the split. `payments` depends on `reservations` (FK to Booking). `reservations` listens for `payments` signals but does not import payments models.

## File layout

```
payments/
├── enums.py
├── models.py
├── services.py        # PaymentScheduler, RefundService
├── webhooks/
│   ├── __init__.py
│   ├── base.py        # WebhookDispatcher, signature verification, persist-first logic
│   └── flywire.py     # Flywire-specific parser + URL view
├── tasks.py           # Celery: retry, reconciliation, scheduled charge for tokenized cards
├── signals.py         # payment_succeeded, payment_failed, payment_refunded
└── urls.py            # /webhooks/payments/<provider_slug>/
```

## Models

### `Payment(SoftDeleteModel)`
**One model, one status enum, one purpose enum** — replaces the three legacy status enums (`InitialPaymentStatus`, `BalancePaymentStatus`, `DepsitPaymentStatus`).

- `reference` — CharField(unique)  # e.g. `P-2026-000123`
- `booking` — FK reservations.Booking PROTECT
- `purpose` — TextChoices (`DEPOSIT`, `BALANCE`, `SECURITY_DEPOSIT`, `REFUND`, `ADJUSTMENT`)
- `status` — TextChoices (`PENDING`, `PROCESSING`, `SUCCEEDED`, `FAILED`, `REFUNDED`, `CANCELLED`, `EXPIRED`)
- `amount` — Decimal(12, 2)
- `currency` — FK pricing.Currency PROTECT
- `provider` — TextChoices (`FLYWIRE`, `MANUAL_BANK_TRANSFER`, `STRIPE`)  # extensible
- `provider_reference` — CharField(blank=True)
- `payment_method` — TextChoices (`CARD`, `BANK_TRANSFER`, `OTHER`)
- `token` — CharField(blank=True)  # tokenised card if held
- `signature` — CharField(blank=True)  # webhook signature for one-time receipts
- `idempotency_key` — CharField(unique)
- `due_at` — DateTimeField(null=True, blank=True)
- `requested_at` — DateTimeField(null=True, blank=True)
- `settled_at` — DateTimeField(null=True, blank=True)
- `failure_reason` — CharField(blank=True)
- `meta` — JSONField(default=dict)  # provider-specific blob

Indexes: `(booking, purpose)`, `(status, due_at)`, `provider_reference`.

Constraints:
- `UniqueConstraint(booking, purpose, condition=Q(status__in=["PENDING","PROCESSING","SUCCEEDED"]), name="unique_active_payment_per_purpose")` — a booking has at most one active payment per purpose (refunds and adjustments are separate purposes).

### `PaymentLine(TimestampedModel)`
For payments that allocate across multiple line items (rare; mostly bookings have a single line per payment).
- `payment` — FK CASCADE
- `description` — CharField
- `amount` — Decimal(12, 2)

### `PaymentEvent(TimestampedModel)`
Append-only audit. Replaces the legacy `PaymentStatusLog`.
- `payment` — FK Payment PROTECT
- `from_status`, `to_status` — TextChoices
- `source` — TextChoices (`WEBHOOK`, `ADMIN`, `SYSTEM`, `USER`)
- `actor` — FK User SET_NULL, null=True
- `delivery` — FK WebhookDelivery SET_NULL, null=True (when source=WEBHOOK)
- `payload_hash` — CharField(blank=True)
- `meta` — JSONField(default=dict)

### `WebhookDelivery(TimestampedModel)`
Persist-first inbound log. Idempotency anchor.
- `provider` — TextChoices
- `event_id` — CharField  # provider's event id
- `signature` — CharField
- `signature_valid` — BooleanField(default=False)
- `raw_body` — TextField
- `headers` — JSONField(default=dict)
- `received_at` — DateTimeField(default=now)
- `processed_at` — DateTimeField(null=True, blank=True)
- `processing_error` — TextField(blank=True)
- `retry_count` — PositiveSmallInteger(default=0)
- `payment` — FK Payment SET_NULL, null=True  # set when dispatched

Constraint: `UniqueConstraint(provider, event_id)` — provider re-delivery is a no-op.

## Services

### `PaymentScheduler` (in `payments/services.py`)
At `Booking` creation, generates the schedule from the effective `PropertyFinance.payment_schedule`:

```python
@classmethod
def create_for_booking(cls, booking) -> list[Payment]:
    schedule = booking.property.finance.effective_payment_schedule()
    sd_policy = booking.property.finance.effective_security_deposit_policy()
    payments = []
    if schedule.deposit_required:
        payments.append(Payment(
            booking=booking, purpose="DEPOSIT", status="PENDING",
            amount=cls._calc_deposit(booking, schedule),
            due_at=now(),    # deposit is immediate
            currency=booking.currency,
            idempotency_key=f"deposit:{booking.reference}",
        ))
    if schedule.interim_required:
        payments.append(...)
    payments.append(Payment(
        booking=booking, purpose="BALANCE", status="PENDING",
        amount=booking.balance_due,
        due_at=booking.balance_due_at,
        ...
    ))
    if sd_policy.is_required:
        payments.append(...)
    Payment.objects.bulk_create(payments)
    return payments
```

### `RefundService`
Handles partial/full refunds — creates a `Payment` row with `purpose=REFUND` (negative amount semantics handled via the status; the amount stays positive, refunds are tracked by purpose+status).

## Webhook flow

### URL
`/webhooks/payments/<provider_slug>/` — provider read from URL, not from a hardcoded `VC` prefix in the body parser.

### Request handling
1. **Persist first**: in a single atomic block, create `WebhookDelivery(provider, event_id, raw_body, headers, signature)`. The `UniqueConstraint(provider, event_id)` means a replay throws `IntegrityError` — catch it, return 200 with the previous delivery's result. Provider re-delivery is safe.
2. **Verify signature**: HMAC-SHA256 over `raw_body` using `settings.PAYMENT_WEBHOOK_SECRETS[provider]`. Mark `signature_valid` on the delivery. On failure: log + return 401.
3. **Enqueue**: dispatch a Celery task `process_webhook_delivery(delivery_id)`. Return 200 immediately so the provider doesn't time out on our business logic.
4. **Process** (Celery): load delivery, parse payload via provider-specific parser to a normalised `ProviderEvent` dataclass (event_kind, payment_reference, amount, currency, settled_at, raw), look up the `Payment` by `idempotency_key` or `provider_reference`, apply a status transition via `Payment.transition_to(new_status, source="WEBHOOK", delivery=delivery)`. The transition writes a `PaymentEvent` and fires a Django signal.
5. **Retries**: Celery autoretries on transient errors with exponential backoff (max 6 attempts, ~1h). `WebhookDelivery.retry_count` tracks attempts. After exhaustion, alert via Sentry.

### Outbound calls
We never call providers from a request thread for state-changing ops. Tokenised-card charges (auto-balance) and security-deposit captures/refunds go through Celery with retries and a circuit breaker.

## Signal contract (reservations <- payments)

Reservations registers handlers for:

- `payment_succeeded(payment)` — handler dispatches to `Booking.record_deposit(payment)` or `Booking.record_balance(payment)` based on `payment.purpose`.
- `payment_failed(payment)` — handler may transition booking to `CANCELLED` (deposit failure) or notify ops (balance failure with retry pending).
- `payment_refunded(payment)` — handler triggers downstream booking logic (e.g. update `Booking.adjustment`).

No reverse dependency: payments never imports reservations models. Reservations imports payments only inside `signals.py` and `services.py`.

## Booking ↔ Payment coupling

- `Payment.booking` is a real FK with `on_delete=PROTECT`. Deletion of a booking with payments is blocked; cancellation uses soft-delete + refund flow.
- `Booking.balance_due` lives on the booking (denormalised total) but the authoritative outstanding amount is computed by summing payments by purpose+status. Service helper: `Booking.outstanding_balance() -> Decimal`.

## Dropped from legacy

- `InitialPaymentStatus`, `BalancePaymentStatus`, `DepsitPaymentStatus` — three enums collapsed into `Payment.purpose` + `Payment.status`.
- `VillaCheckoutDetail.IPDDate`, `RBDate`, `SDStatus` etc — those dates are now `due_at`/`settled_at` on the respective Payment rows.
- Hardcoded `VC` prefix webhook parser — replaced by URL-routed `<provider_slug>` dispatch.
- `VillaPayment.Token` exposed everywhere — only the active card-on-file token lives on the booking (or a separate `BookingPaymentMethod` if multi-method ever lands).

## Security notes

- Webhook secrets in env / Vault, never in DB.
- HMAC verified on raw body bytes (not the JSON re-encoded — guard against re-encoding mismatches).
- Tokens never logged; admin views mask them.
- Payment events are append-only; no admin `delete` permission in production.
