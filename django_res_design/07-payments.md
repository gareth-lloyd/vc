# 07 — Payments

Separate app — webhook surface and audit boundary justify the split. `payments` depends on `reservations` (FK to Booking). `reservations` listens for `payments` signals but does not import payments models.

## File layout

```
payments/
├── enums.py
├── models.py
├── services.py        # PaymentScheduler, RefundService, SecurityDepositService
├── webhooks/
│   ├── __init__.py
│   ├── base.py        # WebhookDispatcher, signature verification, persist-first logic
│   └── flywire.py     # Flywire-specific parser + URL view
├── tasks.py           # Celery: retry, reconciliation, scheduled charge for tokenized cards
├── signals.py         # payment_succeeded, payment_failed, payment_refunded
└── urls.py            # /webhooks/payments/<provider_slug>/
```

## Models

### `Payment(AuditedModel)`
Lifecycle lives entirely in the `status` enum below — no soft delete. Terminal states (`SUCCEEDED`, `FAILED`, `REFUNDED`, `CANCELLED`, `EXPIRED`) stay on the row and are visible to every query; nothing is hidden behind a manager. **One model, one status enum, one purpose enum** — replaces the three legacy status enums (`InitialPaymentStatus`, `BalancePaymentStatus`, `DepsitPaymentStatus`).

- `reference` — CharField(unique)  # e.g. `P-2026-000123`
- `booking` — FK reservations.Booking PROTECT
- `purpose` — TextChoices (`DEPOSIT`, `BALANCE`, `SECURITY_DEPOSIT`, `CONCIERGE`, `REFUND`, `ADJUSTMENT`)
- `status` — TextChoices (`PENDING`, `PROCESSING`, `SUCCEEDED`, `FAILED`, `REFUNDED`, `CANCELLED`, `EXPIRED`, `WAIVED`)  # `WAIVED` is operator-applied to a scheduled `DEPOSIT` or `BALANCE` row that has been forgiven — see `:waive` transition below and reconciliation issue #24. `WAIVED` is terminal: the row is no longer collectible. Not applicable to `SECURITY_DEPOSIT` (which has its own track model — see `SecurityDeposit` below), `REFUND`, or `ADJUSTMENT`.
- `amount` — Decimal(12, 2)
- `currency` — FK pricing.Currency PROTECT
- `provider` — TextChoices (`FLYWIRE`, `MANUAL_BANK_TRANSFER`)  # extensible — Flywire is the only online gateway in v1; the enum is left open for a future second provider but no other gateway code paths are built. See `10-decisions.md`.
- `provider_reference` — CharField(blank=True)
- `payment_method` — TextChoices (`CARD`, `BANK_TRANSFER`, `OTHER`)
- `token` — CharField(blank=True)  # tokenised card if held
- `signature` — CharField(blank=True)  # webhook signature for one-time receipts
- `due_at` — DateTimeField(null=True, blank=True)
- `requested_at` — DateTimeField(null=True, blank=True)
- `settled_at` — DateTimeField(null=True, blank=True)
- `failure_reason` — CharField(blank=True)
- `meta` — JSONField(default=dict)  # provider-specific blob
- `concierge_item` — FK reservations.BookingConciergeItem SET_NULL, null=True, blank=True — set on `purpose=CONCIERGE` rows so each concierge invoice traces back to its source line item; null on every other purpose

Indexes: `(booking, purpose)`, `(status, due_at)`, `provider_reference`.

Constraints:
- `UniqueConstraint(booking, purpose, condition=Q(status__in=["PENDING","PROCESSING","SUCCEEDED"]) & Q(purpose__in=["DEPOSIT","BALANCE"]), name="unique_active_payment_per_purpose")` — at most one active payment per (booking, purpose) for `DEPOSIT` and `BALANCE`. `SECURITY_DEPOSIT` is **not** constrained here: a single `SecurityDeposit` workflow may produce multiple `Payment(purpose=SECURITY_DEPOSIT)` rows (one for the pre-auth charge, one for a subsequent capture, one for a manual-BT receipt, etc.); the active-row invariant is enforced by the `SecurityDeposit` model itself (one active SD per booking). `CONCIERGE`, `REFUND`, and `ADJUSTMENT` are also unconstrained — a booking may legitimately have many concierge invoices over the stay, and refunds/adjustments may produce many gateway-transaction rows over retries.

#### Operator-applied transitions: `:waive` and `:mark-paid`

The API exposes `POST /bookings/{id}/deposit:waive`, `/balance:waive`, `:mark-paid` on deposit/balance/security tracks (§2.10–2.12). The backend transitions for the **deposit** and **balance** tracks act on the scheduled `Payment(purpose ∈ {DEPOSIT, BALANCE})` row directly:

| From | Action | To | Required actor | Side effects |
|---|---|---|---|---|
| `PENDING` / `PROCESSING` | `waive(reason)` | `WAIVED` | user with `payments.payment.waive` perm | set `failure_reason="WAIVED:<reason>"`, write `PaymentEvent(kind=WAIVED, actor, meta={"reason": …})`, fire `payment_waived(payment)` signal so reservations advances the booking (deposit-waive → treat as `record_deposit`; balance-waive → treat as `record_balance` for outstanding-balance accounting). `WAIVED` is terminal. |
| `PENDING` | `mark_paid(amount, paid_at, method, reference, notes)` | `SUCCEEDED` | user with `payments.payment.mark_paid` perm | record manual receipt: set `provider=MANUAL_BANK_TRANSFER` (or `provider=OTHER` for cash/cheque), `payment_method` from input, `provider_reference` from input, `settled_at=paid_at`, `signature=""`, write `PaymentEvent(kind=MARK_PAID, actor)`, fire `payment_succeeded(payment)` signal (so reservations advances `record_deposit` / `record_balance` the same way it would for a gateway-confirmed payment). |

`:mark-paid` is **not** a generic "force any status to SUCCEEDED" — it is the manual-bank-transfer / cash-receipt shortcut. The operator entering the receipt is the system-of-record; no gateway webhook will follow. The existing `MANUAL_BANK_TRANSFER` provider value covers the bank-transfer case; cash and cheque receipts use `provider=OTHER` with `payment_method ∈ {OTHER}` plus structured `provider_reference` (the cheque number / cash-receipt id).

For the **security-deposit** track, `:mark-paid` does not act on a `Payment` row — it advances the parent `SecurityDeposit` workflow row (see below) along its BT-refundable path. The security track has no `:waive` action; if a property's `SecurityDepositPolicy.is_required = False`, no `SecurityDeposit` row is ever created.

See reconciliation issue #24.

### `PaymentLine(TimestampedModel)`
For payments that allocate across multiple line items (rare; mostly bookings have a single line per payment).
- `payment` — FK CASCADE
- `description` — CharField
- `amount` — Decimal(12, 2)

### `SecurityDeposit(AuditedModel)`
First-class workflow object for the security-deposit lifecycle. Mirrors the `Refund` shape: the **workflow row** owns the state machine and the operator-facing actions (`:hold`, `:release`, `:claim`, `:mark-paid`, `:request-payment`); the gateway-transaction audit lives on spawned `Payment(purpose=SECURITY_DEPOSIT)` rows (one per pre-auth attempt, capture, or BT refund) linked back via `meta['security_deposit_id']`. The `SecurityDeposit` itself never talks to the gateway directly. This is the same pattern as `Refund`.

The legacy `Payment.status` enum cannot express the pre-auth lifecycle on its own — `AUTHORIZED` / `HELD` / `CAPTURED` are distinct from the inbound-charge `PENDING` / `PROCESSING` / `SUCCEEDED` states. Promoting the security-deposit lifecycle into its own model lets the state machine carry the workflow shape without inflating `Payment.status` with states that only apply to one purpose.

- `reference` — CharField(unique)  # e.g. `SD-2026-000045`
- `booking` — FK reservations.Booking PROTECT (at most one active `SecurityDeposit` per booking enforced by a partial unique constraint scoped to non-terminal `status`; cancellation/replacement transitions the prior row into a terminal state like `EXPIRED` or `FAILED` — the row stays visible, the new row is the active one)
- `kind` — TextChoices (`PRE_AUTH_HOLD`, `BT_REFUNDABLE`) — chosen at creation from `SecurityDepositPolicy.kind`; once set, drives the allowed transitions (see below)
- `amount` — Decimal(12, 2)
- `currency` — FK pricing.Currency PROTECT
- `status` — TextChoices (`AWAITING_DETAILS`, `PRE_AUTHED`, `RELEASED`, `CAPTURED`, `EXPIRED`, `FAILED`, `AWAITING_BT`, `HELD`, `REFUNDED`, `PARTIALLY_REFUNDED`) — first six are the pre-auth path; last four are the BT-refundable path. `NOT_APPLICABLE` is **not** a status here — when no SD is required, no row exists.
- `due_at` — DateTimeField(null=True, blank=True)  # when card details / BT must arrive by
- `hold_expires_at` — DateTimeField(null=True, blank=True)  # pre-auth hold expiry returned by the gateway
- `release_after_departure_days` — PositiveSmallInteger(null=True, blank=True)  # snapshot from `SecurityDepositPolicy`
- `release_scheduled_for` — DateField(null=True, blank=True)  # derived: `Booking.date_to + release_after_departure_days`
- `released_at` — DateTimeField(null=True, blank=True)
- `captured_amount` — Decimal(12, 2, null=True, blank=True)  # set when `kind=PRE_AUTH_HOLD` is partially or fully captured against damages
- `refunded_amount` — Decimal(12, 2, null=True, blank=True)  # set on the BT-refundable path as refunds accumulate
- `damage_claim` — FK reservations.DamageClaim SET_NULL, null=True, blank=True  # link to the structured claim that justifies a capture / partial refund. (`DamageClaim` ships in `reservations/models/damage_claim.py`, BUG-008; `SecurityDepositService.claim()` resolves + booking-validates it. The damages *workflow* — report sub-form, photos, threshold permissions, the damages email, the enforced approval state machine — is deferred to workflow 8/17.)
- `requested_by` — FK User SET_NULL, null=True, related_name="security_deposits_requested"
- `requested_at` — DateTimeField(default=now)
- `meta` — JSONField(default=dict)

Indexes: `(booking, status)`, `(status, release_scheduled_for)`, `(status, hold_expires_at)`.

Constraints:
- `CheckConstraint(amount > 0)`
- `UniqueConstraint(booking, condition=~Q(status__in=["RELEASED", "EXPIRED", "FAILED", "REFUNDED"]), name="one_active_security_deposit_per_booking")` — at most one non-terminal SecurityDeposit per booking. Replaced/cancelled rows transition into a terminal status and stay visible; they no longer block creating a fresh row.

#### State machine — pre-auth hold path (`kind=PRE_AUTH_HOLD`)

```
AWAITING_DETAILS ──:hold──▶ PRE_AUTHED ──:release──▶ RELEASED  (terminal)
                                  │
                                  ├──:claim──▶ CAPTURED   (terminal)
                                  │
                                  └──(hold_expires_at past, gateway voided)──▶ EXPIRED (terminal)

AWAITING_DETAILS or PRE_AUTHED ──(gateway error)──▶ FAILED  (terminal; ops opens new SD row to retry)
```

| From | Action | To | Required actor | Side effects |
|---|---|---|---|---|
| (creation) | (system) | `AWAITING_DETAILS` | system at booking creation | created with `due_at`, `release_after_departure_days` snapshotted from `SecurityDepositPolicy` |
| `AWAITING_DETAILS` | `:hold` | `PRE_AUTHED` | user (or webhook from hosted-fields gateway return) | create `Payment(purpose=SECURITY_DEPOSIT, status=SUCCEEDED, provider=FLYWIRE, amount=…, meta.security_deposit_id=…)` recording the pre-auth charge; set `hold_expires_at` from gateway response. Note: the `Payment.status=SUCCEEDED` here means "the pre-auth call succeeded", not "the money has moved" — the money sits on the card as a hold. |
| `PRE_AUTHED` | `:release` | `RELEASED` | user with `payments.security_deposit.release` perm, **or** Celery beat task on/after `release_scheduled_for` | call gateway to void the hold via Celery; on success set `released_at`, fire `security_deposit_released(sd)` signal. |
| `PRE_AUTHED` | `:claim` | `CAPTURED` | user with `payments.security_deposit.claim` perm | requires `damage_claim` FK to be set; call gateway to capture (full or partial — partial requires `captured_amount` ≤ `amount` and writes the difference back as a release on the residual). One `Payment(purpose=SECURITY_DEPOSIT, status=SUCCEEDED)` per capture transaction; the original pre-auth Payment is left untouched as audit. |
| `PRE_AUTHED` | (Celery beat: `hold_expires_at` past without release) | `EXPIRED` | system | the gateway has already voided the hold — we just reconcile state. Fires `security_deposit_expired(sd)` signal for ops review. |
| `AWAITING_DETAILS` / `PRE_AUTHED` | (gateway failure) | `FAILED` | system | set `failure_reason`. No re-open — ops opens a new `SecurityDeposit` row to retry. |

#### State machine — BT refundable path (`kind=BT_REFUNDABLE`)

```
AWAITING_BT ──:mark-paid──▶ HELD ──(post-departure release)──▶ REFUNDED  (terminal)
                              │
                              └──(partial refund via Refund workflow)──▶ PARTIALLY_REFUNDED (terminal)

AWAITING_BT ──(timeout)──▶ FAILED (terminal)
```

| From | Action | To | Required actor | Side effects |
|---|---|---|---|---|
| (creation) | (system) | `AWAITING_BT` | system at booking creation | guest is asked to wire the SD amount in advance |
| `AWAITING_BT` | `:mark-paid` | `HELD` | user with `payments.payment.mark_paid` perm | record manual receipt: create `Payment(purpose=SECURITY_DEPOSIT, status=SUCCEEDED, provider=MANUAL_BANK_TRANSFER, amount, settled_at, provider_reference, meta.security_deposit_id=…)`. No `payment_succeeded` cascade to `Booking.record_*` — the SD is independent of deposit/balance. |
| `HELD` | (`:release` post-departure — operator action, or Celery beat task on/after `release_scheduled_for`) | `REFUNDED` | user with `payments.security_deposit.release` perm, **or** system | open one `Refund(purpose_track=SECURITY_DEPOSIT, amount=amount, against_payment=<the manual Payment row>)` and execute it. On successful refund, transition to `REFUNDED`, set `released_at`, `refunded_amount=amount`, fire `security_deposit_released(sd)`. |
| `HELD` | (`:claim` — partial refund) | `PARTIALLY_REFUNDED` | user with `payments.security_deposit.claim` perm | requires `damage_claim` FK; opens one `Refund` for `amount - captured_amount`, executes it, sets `refunded_amount`, `captured_amount`, `released_at`. |
| `AWAITING_BT` | (Celery beat: `due_at` past with no receipt) | `FAILED` | system | ops review; booking may be cancelled per policy. |

Notes:
- All transition methods wrap state mutation + `PaymentEvent` row + signal in `transaction.atomic`. `PaymentEvent` is extended to be polymorphic over `Payment` / `Refund` / `SecurityDeposit` — exactly one of those three FKs is set per row (`CheckConstraint`).
- `SECURITY_DEPOSIT_RELEASE` is already enumerated in `Refund.reason_code`; BT-refundable releases re-use the existing refund workflow rather than reinventing it, which keeps approval / audit consistent.
- Pre-auth `:claim` does **not** go through `Refund` — it is a capture against an existing authorization, not a money-return movement. Refund-style separation of duties applies only to BT refunds; pre-auth captures gate on the `damage_claim` link being approved before `:claim` succeeds.
- `SecurityDeposit.kind` is chosen at booking creation from `SecurityDepositPolicy.kind` and is **immutable** — switching paths mid-booking requires soft-deleting the SD and opening a new one.

See reconciliation issue #25.

### `Refund(AuditedModel)`
First-class workflow object for money going back to the guest. Separation-of-duties is the whole point: the person who *requests* a refund must not be the person who *executes* it. The legacy system had no refund workflow — operators issued refunds manually through the gateway dashboard, with no in-app audit trail. This model fixes that.

A `Refund` is the **workflow object**. When it transitions to `EXECUTING` we create one or more `Payment(purpose=REFUND)` rows to record the actual gateway transactions; those Payment rows carry the provider reference, webhook callbacks, and money-movement audit. The Refund itself never directly talks to the gateway.

- `reference` — CharField(unique)  # e.g. `R-2026-000045`
- `booking` — FK reservations.Booking PROTECT
- `against_payment` — FK Payment SET_NULL, null=True, blank=True  # the original inbound Payment being refunded (when known; full vs partial). Null permitted for goodwill refunds not tied to a single inbound charge.
- `purpose_track` — TextChoices (`DEPOSIT`, `BALANCE`, `SECURITY_DEPOSIT`, `ADJUSTMENT`, `GOODWILL`)  # which money track this refund is against; mirrors `Payment.purpose` minus `REFUND`, plus `GOODWILL`
- `amount` — Decimal(12, 2)  # positive; refund direction is implicit
- `currency` — FK pricing.Currency PROTECT
- `status` — TextChoices (`PENDING`, `APPROVED`, `REJECTED`, `EXECUTING`, `SUCCEEDED`, `FAILED`, `CANCELLED`)
- `reason_code` — TextChoices (`CANCELLATION`, `OVERPAYMENT`, `GOODWILL`, `SECURITY_DEPOSIT_RELEASE`, `DUPLICATE_CHARGE`, `OTHER`)
- `reason_notes` — TextField(blank=True)
- `method` — TextChoices (`ONLINE_GATEWAY`, `MANUAL_BANK_TRANSFER`, `OFFLINE`)  # how the money will be returned
- `requested_by` — FK User SET_NULL, null=True, related_name="refunds_requested"
- `requested_at` — DateTimeField(default=now)
- `approved_by` — FK User SET_NULL, null=True, blank=True, related_name="refunds_approved"
- `approved_at` — DateTimeField(null=True, blank=True)
- `rejected_by` — FK User SET_NULL, null=True, blank=True, related_name="refunds_rejected"
- `rejected_at` — DateTimeField(null=True, blank=True)
- `rejection_reason` — TextField(blank=True)
- `executed_by` — FK User SET_NULL, null=True, blank=True, related_name="refunds_executed"  # the actor who triggered `:execute` (distinct from `approved_by` — separation of duties)
- `executed_at` — DateTimeField(null=True, blank=True)
- `cancelled_at` — DateTimeField(null=True, blank=True)
- `settled_at` — DateTimeField(null=True, blank=True)  # gateway-confirmed success
- `failure_reason` — CharField(blank=True)
- `meta` — JSONField(default=dict)

Indexes: `(booking, status)`, `(status, requested_at)`, `against_payment`.

Constraints:
- `CheckConstraint(amount > 0)`.
- `CheckConstraint(approved_by != requested_by OR approved_by IS NULL)` — separation of duties: the requester cannot self-approve. Bypassable only by a dedicated `payments.refund.self_approve` permission for tiny refunds; enforce at the service layer, not the DB, so policy can flex without a migration.
- No DB-level uniqueness across `(booking, against_payment)` — partial refunds and multi-attempt executions both legitimately produce more than one row.

#### State machine

```
                requested
                    ↓
                ┌───────┐
                │PENDING│──────────────────────────┐
                └───────┘                          │
                  │   │                            │
          approve │   │ reject                     │ cancel (by requester, while PENDING)
                  ↓   ↓                            ↓
            ┌────────┐ ┌────────┐             ┌─────────┐
            │APPROVED│ │REJECTED│ (terminal)  │CANCELLED│ (terminal)
            └────────┘ └────────┘             └─────────┘
                  │
        execute   │              cancel (while APPROVED, by approver+ only)
                  ↓                  ↓
             ┌─────────┐         ┌─────────┐
             │EXECUTING│         │CANCELLED│ (terminal)
             └─────────┘
                  │
       gateway    │ gateway
       success    │ failure
                  ↓
            ┌─────────┐  ┌──────┐
            │SUCCEEDED│  │FAILED│ (terminal; ops may open a new Refund to retry)
            └─────────┘  └──────┘
```

Transitions (all wrap in `transaction.atomic`, all write a `PaymentEvent` row scoped to the Refund — see `PaymentEvent` schema note below):

| From | Action | To | Required actor | Side effects |
|---|---|---|---|---|
| `PENDING` | `approve` | `APPROVED` | distinct user from `requested_by`, with `payments.refund.approve` perm | set `approved_by`/`approved_at` |
| `PENDING` | `reject` | `REJECTED` | any user with `payments.refund.approve` perm | set `rejected_by`/`rejected_at`/`rejection_reason` |
| `PENDING` | `cancel` | `CANCELLED` | requester or approver | set `cancelled_at` |
| `APPROVED` | `execute` | `EXECUTING` | user with `payments.refund.execute` perm; **may be `approved_by`** (single op can both authorise the refund and push it to the gateway in low-risk flows; for high-risk/large refunds, an org policy may require `executed_by != approved_by`, enforced in the service, not the model) | create `Payment(purpose=REFUND, status=PROCESSING)` linked via `meta.refund_id`, queue Celery task `process_refund(refund_id)` to call the gateway |
| `APPROVED` | `cancel` | `CANCELLED` | user with `payments.refund.approve` perm | set `cancelled_at` |
| `EXECUTING` | (webhook success) | `SUCCEEDED` | system | set `settled_at`, mark linked `Payment.status=SUCCEEDED`, fire `payment_refunded(payment)` signal |
| `EXECUTING` | (webhook failure / Celery exhaustion) | `FAILED` | system | set `failure_reason`, mark linked `Payment.status=FAILED`. Manual reissue requires a new `Refund` row. |

Notes:
- `REJECTED`, `CANCELLED`, `SUCCEEDED`, `FAILED` are terminal. No re-open path.
- `EXECUTING` is the *outbox state*: the gateway call is in flight via Celery. The state machine never advances directly from `APPROVED` to `SUCCEEDED` without observing the gateway's webhook.
- `against_payment` is enforced sane in the service layer (refund amount cumulative across non-failed refunds must not exceed the original `Payment.amount`); not a DB constraint because cross-row aggregate constraints aren't a thing in Postgres without triggers.

### `PaymentEvent(TimestampedModel)`
Append-only audit. Replaces the legacy `PaymentStatusLog`. Covers `Payment`, `Refund`, and `SecurityDeposit` state transitions — exactly one of the three FKs is set per row.
- `payment` — FK Payment PROTECT, null=True, blank=True
- `refund` — FK Refund PROTECT, null=True, blank=True
- `security_deposit` — FK SecurityDeposit PROTECT, null=True, blank=True
- `from_status`, `to_status` — TextChoices
- `kind` — CharField(blank=True)  # short discriminator for non-status events (`WAIVED`, `MARK_PAID`, `HOLD`, `RELEASE`, `CLAIM`, `EXPIRED`) — empty for ordinary status transitions
- `source` — TextChoices (`WEBHOOK`, `ADMIN`, `SYSTEM`, `USER`)
- `actor` — FK User SET_NULL, null=True
- `delivery` — FK WebhookDelivery SET_NULL, null=True (when source=WEBHOOK)
- `payload_hash` — CharField(blank=True)
- `meta` — JSONField(default=dict)

Constraint: `CheckConstraint(num_nonnull(payment, refund, security_deposit) = 1)` — exactly one of the three FKs is set. (Expressed in SQL as the sum of three `IS NOT NULL` casts equalling 1.)

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

### `RefundService` (in `payments/services.py`)
Coordinates the `Refund` workflow. The `Refund` model is the workflow object; this service owns the transitions, permission checks, and the creation of downstream `Payment(purpose=REFUND)` rows at `:execute` time.

```python
class RefundService:
    @classmethod
    def request(cls, *, booking, amount, currency, purpose_track, reason_code,
                reason_notes="", method="ONLINE_GATEWAY", against_payment=None,
                requested_by) -> Refund:
        """Open a refund in PENDING. Validates cumulative refunds against
        `against_payment.amount` if `against_payment` is set."""

    @classmethod
    def approve(cls, refund, *, actor) -> Refund:
        """PENDING → APPROVED. Asserts actor != refund.requested_by (unless
        actor has `payments.refund.self_approve`)."""

    @classmethod
    def reject(cls, refund, *, actor, reason) -> Refund:
        """PENDING → REJECTED. Terminal."""

    @classmethod
    def cancel(cls, refund, *, actor) -> Refund:
        """PENDING or APPROVED → CANCELLED. Terminal."""

    @classmethod
    def execute(cls, refund, *, actor) -> Refund:
        """APPROVED → EXECUTING. Creates one `Payment(purpose=REFUND,
        status=PROCESSING)` linked via `meta['refund_id']`, queues Celery
        `process_refund(refund_id)`."""

    @classmethod
    def from_cancellation(cls, booking, *, reason, requested_by) -> Refund | None:
        """Opens a `Refund` row (in PENDING) sized as
        `paid_total - cancellation_fee`, where `paid_total` is the sum of
        `Payment(status=SUCCEEDED, purpose IN (DEPOSIT, BALANCE))` and
        `cancellation_fee` is resolved from the property's
        `CancellationPolicy` (see `03-finance-config.md`):

            fee = max(cancellation_fee_amount,
                      cancellation_fee_percent * paid_total)

        Returns `None` (no refund row created) when `paid_total <= fee`.
        Called by `Booking.cancel(reason)` on bookings that have any
        SUCCEEDED inbound payment. Security-deposit money is **not**
        rolled into this refund — the `SecurityDeposit` workflow runs
        its own release/refund path and continues independently."""
```

Webhook callbacks land on the spawned `Payment` row first (via the normal payment-webhook flow). The `payment_refunded` / `payment_failed` receivers in `payments/signals.py` inspect `payment.meta['refund_id']` and delegate to `RefundService.sync_from_outbound_payment`, which advances the Refund `EXECUTING → SUCCEEDED|FAILED` (idempotent: missing or already-terminal refunds are a logged no-op). Refunds never get their own webhook URL — they ride on the Payment webhook pipeline.

### `SecurityDepositService` (in `payments/services.py`)
Coordinates the `SecurityDeposit` workflow. Like `RefundService`, this owns the state machine transitions, permission checks, and the creation of downstream `Payment` rows that record gateway transactions.

```python
class SecurityDepositService:
    @classmethod
    def create_for_booking(cls, booking) -> SecurityDeposit | None:
        """Called by PaymentScheduler. Reads `SecurityDepositPolicy` from
        property finance; if `is_required`, opens an SD row in either
        `AWAITING_DETAILS` (`PRE_AUTH_HOLD`) or `AWAITING_BT` (`BT_REFUNDABLE`)."""

    @classmethod
    def hold(cls, sd, *, gateway_response, actor) -> SecurityDeposit:
        """AWAITING_DETAILS → PRE_AUTHED. Creates `Payment(purpose=SECURITY_DEPOSIT,
        status=SUCCEEDED, provider=..., meta.security_deposit_id=sd.id)`."""

    @classmethod
    def mark_paid(cls, sd, *, amount, paid_at, method, reference, actor) -> SecurityDeposit:
        """AWAITING_BT → HELD. Creates `Payment(purpose=SECURITY_DEPOSIT,
        status=SUCCEEDED, provider=MANUAL_BANK_TRANSFER, ...)`."""

    @classmethod
    def release(cls, sd, *, actor) -> SecurityDeposit:
        """PRE_AUTHED → RELEASED  (void hold via gateway, async)
        HELD       → REFUNDED   (open & execute Refund(purpose_track=SECURITY_DEPOSIT))"""

    @classmethod
    def claim(cls, sd, *, damage_claim, captured_amount, actor) -> SecurityDeposit:
        """PRE_AUTHED → CAPTURED         (capture against pre-auth)
        HELD       → PARTIALLY_REFUNDED (Refund for amount - captured_amount)"""

    @classmethod
    def expire(cls, sd, *, actor=None) -> SecurityDeposit:
        """PRE_AUTHED → EXPIRED   (system: gateway voided hold)
        AWAITING_BT → FAILED    (system: BT never arrived by due_at)"""
```

The pre-auth gateway calls (hold / capture / void) run through Celery with retry; the service enqueues the task and the webhook-driven status reconciliation updates the SD row once the gateway confirms. BT releases delegate to `RefundService.execute()` so separation-of-duties applies to BT refunds the same way it applies to any other refund.

## Webhook flow

### URL
`/webhooks/payments/<provider_slug>/` — provider read from URL, not from a hardcoded `VC` prefix in the body parser.

### Request handling
1. **Persist first**: in a single atomic block, create `WebhookDelivery(provider, event_id, raw_body, headers, signature)`. The `UniqueConstraint(provider, event_id)` means a replay throws `IntegrityError` — catch it, return 200 with the previous delivery's result. Provider re-delivery is safe.
2. **Verify signature**: HMAC-SHA256 over `raw_body` using `settings.PAYMENT_WEBHOOK_SECRETS[provider]`. Mark `signature_valid` on the delivery. On failure: log + return 401.
3. **Enqueue**: dispatch a Celery task `process_webhook_delivery(delivery_id)`. Return 200 immediately so the provider doesn't time out on our business logic.
4. **Process** (Celery): load delivery, parse payload via provider-specific parser to a normalised `ProviderEvent` dataclass (event_kind, payment_reference, amount, currency, settled_at, raw), look up the `Payment` by `reference` or `provider_reference`, apply a status transition via `Payment.transition_to(new_status, source="WEBHOOK", delivery=delivery)`. The transition writes a `PaymentEvent` and fires a Django signal.
5. **Retries**: Celery autoretries on transient errors with exponential backoff (max 6 attempts, ~1h). `WebhookDelivery.retry_count` tracks attempts. After exhaustion, alert via Sentry.

### Outbound calls
We never call providers from a request thread for state-changing ops. Tokenised-card charges (auto-balance) and security-deposit captures/refunds go through Celery with retries and a circuit breaker.

## Signal contract

All receivers live in **payments** (`payments/signals.py`, registered from `PaymentsConfig.ready()`): payments sits above reservations in the import spine, so a payments-side receiver calling into `Booking` is a clean downward edge, while a reservations-side receiver would be an illegal upward import. The receivers are defensive — an `InvalidTransition` (duplicate settlement, cancelled booking, out-of-order balance) is logged as `payment.booking_advance_skipped` and swallowed, never raised.

- `payment_succeeded(payment)` — `_advance_booking_on_payment_settled` dispatches to `Booking.record_deposit(payment)` or `Booking.record_balance(payment)` based on `payment.purpose` (DEPOSIT/BALANCE only; SD, concierge and adjustment settlements never touch booking state).
- `payment_failed(payment)` — for `Payment(purpose=REFUND)` rows carrying `meta['refund_id']`, `_sync_refund_on_outbound_payment` advances the parent Refund `EXECUTING -> FAILED` (copying `failure_reason`). No booking-state change on ordinary payment failure (ops is notified via comms).
- `payment_refunded(payment)` — fired when a `Payment(purpose=REFUND)` reaches `SUCCEEDED` (and when an ordinary payment reaches `REFUNDED`). `_sync_refund_on_outbound_payment` advances the parent `Refund` to `SUCCEEDED` (stamping `settled_at`) when `payment.meta['refund_id']` is set; rows without a refund id are ignored. Non-gateway refund methods settle their outbound Payment synchronously inside `RefundService.execute`, completing through this same path. (SD `REFUNDED`/`PARTIALLY_REFUNDED` advancement on SD-track refunds remains future work.)
- `payment_waived(payment)` — fired by `Payment.waive()`. Connected to the same `_advance_booking_on_payment_settled` receiver — waiving advances the booking workflow exactly as if the payment had succeeded, just without any money having moved.
- `security_deposit_released(sd)`, `security_deposit_expired(sd)` — fired by `SecurityDepositService` for ops-side notifications. Not consumed by `reservations` (no booking-state change), but useful for the notifications and reporting apps.

No upward dependency: reservations never imports payments. Payments reaches *down* into reservations (lazy imports inside its receivers), the same direction as `_schedule_payments_on_booking_confirmed` and `_expire_payments_on_booking_expired` (which expires a booking's leftover PENDING payments when `expire_bookings` ages it out).

## Booking ↔ Payment coupling

- `Payment.booking` is a real FK with `on_delete=PROTECT`. Deletion of a booking with payments is blocked; cancellation transitions the booking to `CANCELLED` and runs the refund flow. There is no soft-delete path — both `Payment` and `Refund` express their lifecycle via the `status` enum.
- `Booking.balance_due` lives on the booking (denormalised total) but the authoritative outstanding amount is computed by summing payments by purpose+status. Service helper: `Booking.outstanding_balance() -> Decimal`. `Payment(purpose=CONCIERGE)` rows are **excluded** from outstanding-balance maths — concierge invoices are tracked alongside the booking but settle independently of the deposit/balance schedule.
  - **As implemented (2026-06)**: `/bookings` list + detail expose `total` (a serializer alias of the denormalised `balance_due` — the guest-facing gross) and `amount_paid` (sum of `SUCCEEDED` `DEPOSIT`/`BALANCE` rows; `SECURITY_DEPOSIT` and `CONCIERGE` excluded). The sum is annotated in `reservations/views/booking.py::_with_amount_paid` with a per-instance fallback in `BookingListSerializer.get_amount_paid`; both spell the status/purpose values as string literals because `reservations` sits below `payments` in the import spine. The annotation is deliberately gated to `list`/`retrieve` — its payments LEFT JOIN must not leak into `StatusCountsMixin` (`Count("id")` would count booking x payment rows). `Booking.outstanding_balance()` is **not yet built**; the SPA derives `due = total − amount_paid` (`frontend/src/features/bookings/finance.ts`). Known gap: executed refunds do not subtract — `RefundService.execute` creates a separate `purpose=REFUND` row and the source payment keeps `SUCCEEDED` unless a provider webhook flips it to `REFUNDED`, so a refunded booking still reports the pre-refund `amount_paid`.
- **Deposit fields**: `Booking` no longer carries `deposit_amount` / `deposit_percentage` columns (dropped per reconciliation issue #45). The deposit configuration lives on `PropertyFinance.deposit_*` (per `03-finance-config.md`); the deposit-track *state* lives on the `Payment(purpose=DEPOSIT)` row created by `PaymentScheduler.create_for_booking()`. `Booking.pricing_snapshot` retains the deposit figure at confirmation time as part of the locked-in JSON breakdown, but the operational source of truth for "what is owed / what is paid / what is waived" is the `Payment` row. API consumers read this via `GET /bookings/{id}/deposit` (§2.10) or `GET /payments?booking=…&purpose=DEPOSIT`.

## Concierge payments

`workflows/09-booking/booking-concierge.md` describes ad-hoc charges raised against a booking during the stay (extra airport transfer, in-villa chef, last-minute excursion). These don't fit the 3-tier deposit/balance/security schedule:

```python
class ConciergeService:  # in reservations/services.py — placed here for cross-ref
    @classmethod
    def request_payment(
        cls,
        *,
        booking,
        items: list[BookingConciergeItem],
        due_at=None,
        method="ONLINE_GATEWAY",
        actor,
    ) -> Payment:
        """Create one Payment(purpose=CONCIERGE, status=PENDING) totalling
        the items' snapshot prices. The first item's PK populates
        Payment.concierge_item for traceability; additional items are
        recorded on the PaymentLine set. Emits a `concierge_payment_requested`
        signal consumed by `comms` to send the guest an invoice email."""
```

The Concierge service lives in `reservations/` so it can mutate `BookingConciergeItem.status`, but it talks to `payments` only by creating rows — no reverse import.

## New vs legacy

- **`Refund` workflow** — the legacy app had no in-app refund concept at all (zero refund tables in `live-db-24-apr.sql`; no refund-related Blazor pages; cancellation-policy refund percentages were the only "refund" tokens in the schema). Operators issued refunds manually through the gateway dashboard with no audit trail. The new `Refund` model fills this gap and bakes in separation of duties (request vs approve vs execute). See `09-departures.md` for the legacy-mapping note.
- **`SecurityDeposit` workflow** — mirrors `Refund`: a dedicated workflow model with its own state machine, distinct from the `Payment` ledger. Legacy `VillaFinance.SecurityDeposit*` config columns drove a flat `IsSDPaid` flag on `VillaBooking` with no lifecycle — no pre-auth state, no release scheduling, no claim audit. The new `SecurityDeposit` covers both the pre-auth-hold path (`AWAITING_DETAILS` / `PRE_AUTHED` / `RELEASED` / `CAPTURED` / `EXPIRED` / `FAILED`) and the BT-refundable path (`AWAITING_BT` / `HELD` / `REFUNDED` / `PARTIALLY_REFUNDED`). Gateway-transaction audit lives on spawned `Payment(purpose=SECURITY_DEPOSIT)` rows. BT refunds delegate to `Refund` so separation-of-duties applies uniformly. See reconciliation issue #25.
- **`Payment.waive` / `Payment.mark_paid`** — operator-applied transitions on a scheduled deposit/balance `Payment` row, backing the API's `:waive` and `:mark-paid` actions. The legacy app handled both via free-text columns and a `IsBankPaid` boolean with no audit trail; the new model adds `WAIVED` as a terminal status and writes `PaymentEvent` rows for each transition. See reconciliation issue #24.
- **Idempotency moved off the model** — the legacy `Payment.idempotency_key` column (and the parallel columns on `Refund` and `SecurityDeposit`) are removed. The generic `core.IdempotencyRecord` table + DRF middleware (see `00-conventions.md` "Idempotency") covers every unsafe POST including payment creation, refund creation, and security-deposit creation. The model dedup is no longer the responsibility of the payments app. See reconciliation issue #39. **(Superseded 2026-07-02, FG-005: the generic table + middleware were never built and `IdempotencyRecord` is dropped; live dedupe is the service-layer `idempotency_key` → `meta` stamping via `core/idempotency.py`, with DB backstops per FG-010.)**

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
