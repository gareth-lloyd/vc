# 03 — Property Finance Configuration

Models the per-property and per-group financial configuration that the legacy `VillaFinance` god object embedded inline on `VillaMaster`. Lives inside the `properties` app under `models/finance.py`.

## Approach

- One flat model — `PropertyFinance` — OneToOne with `Property`. All fields (commission, tax, bank account, payment schedule, security-deposit policy) sit directly on it as nullable columns.
- One mirror — `GroupFinance` — OneToOne with `PropertyGroup`. Same field set but **non-nullable with sensible defaults**: the group is the floor.
- **Inheritance via null fields**: leave a value `NULL` on the property-level model to fall back to the group's value. The `effective_*()` resolvers on `PropertyFinance` do the merge.

Reconciliation note: an earlier draft split `PropertyFinance` into five OneToOne children (`Commission`, `TaxPolicy`, `BankAccount`, `PaymentSchedule`, `SecurityDepositPolicy`) plus five `Group*` mirrors. That split was justified solely by anticipated per-concern permissions (e.g. `can_view_bank_account` separate from `can_view_commission`). MVP staff roles (`ADMIN` / `RESERVATIONS` / `ACCOUNTS` / `VIEWER` per `01-accounts.md` and reconciliation issue #9) gate the finance form as a whole, not individual sub-concerns. The 5+5 split has been collapsed to 1+1. See reconciliation issue #36.

## `PropertyFinance(AuditedModel)`

OneToOne with `Property`. All operator-editable fields are nullable; `NULL` means "inherit from `GroupFinance`".

### Anchor
- `property` — OneToOne Property CASCADE primary_key
- `season` — FK `pricing.RatePlan` SET_NULL, null=True (legacy `SeasonId`; ties finance to a rate plan in rare cases)
- `contact` — FK accounts.Person PROTECT, null=True — financial recipient (owner who gets paid)
- `parent` — self-FK null=True (legacy `ParentId`; allows finance overrides for a sub-period referencing a parent finance config)
- `notes` — TextField(blank=True)

### Commission
- `commission_calculation_type` — TextChoices (`PERCENT`, `FIXED`), null=True
- `commission_amount` — DecimalField(12, 2, null=True, blank=True)
- `commission_note` — TextField(blank=True)

### Tax
- `tax_number` — CharField(blank=True)
- `tax_is_exempt` — BooleanField(null=True)
- `tax_percentage` — DecimalField(5, 2, null=True, blank=True)  # e.g. 20.00 = 20%

`null` `tax_is_exempt` and `null` `tax_percentage` → inherit from `GroupFinance` / country default.

### Bank account
- `bank_account_name` — CharField(blank=True)
- `bank_account_number` — CharField(blank=True)
- `bank_sort_code` — CharField(blank=True)
- `bank_iban` — CharField(blank=True)
- `bank_bic` — CharField(blank=True)
- `bank_name` — CharField(blank=True)
- `bank_address_line_1`, `bank_address_line_2`, `bank_post_code`, `bank_city` — CharField(blank=True)

Encrypt at rest if PII/secrets policy demands (app-layer Fernet wrap on save).

### Payment schedule
- `deposit_required` — BooleanField(null=True)
- `deposit_calculation_type` — TextChoices (`PERCENT`, `FIXED`), null=True
- `deposit_amount` — Decimal(12, 2, null=True, blank=True)
- `interim_required` — BooleanField(null=True)
- `interim_calculation_type` — TextChoices, null=True
- `interim_amount` — Decimal, null=True
- `days_interim_due_before_arrival` — PositiveSmallInteger(null=True)
- `days_balance_due_before_arrival` — PositiveSmallInteger(null=True)

Used by `payments.PaymentScheduler` to derive due dates at booking-creation time.

### Security-deposit policy
- `security_deposit_required` — BooleanField(null=True)
- `security_deposit_calculation_type` — TextChoices (`PERCENT`, `FIXED`), null=True
- `security_deposit_amount` — Decimal(12, 2, null=True)
- `security_deposit_days_due_before_arrival` — PositiveSmallInteger(null=True)
- `security_deposit_days_refunded_after_departure` — PositiveSmallInteger(null=True)
- `security_deposit_payment_method` — TextChoices (`CARD_HOLD`, `CARD_CHARGE`, `BANK_TRANSFER`), null=True

### Cancellation policy
Cancellation refund mechanics. `workflows/09-booking/booking-cancellation.md` and `booking-modification.md` resolve refund maths against these fields; `payments.RefundService.from_cancellation()` (see `07-payments.md`) computes the actual `Refund` row sized as `paid_total - max(cancellation_fee_amount, cancellation_fee_percent * paid_total)`.

- `cancellation_fee_amount` — Decimal(12, 2, null=True, blank=True) — flat fee floor; null = no flat floor
- `cancellation_fee_percent` — Decimal(5, 2, null=True, blank=True) — % of paid total; null = no percent component
- `cancellation_window_days` — PositiveSmallInteger(null=True, blank=True) — number of days before arrival inside which the fee applies. Cancellations earlier than this window may waive the fee entirely (operator-configurable via a future `pre_window_fee_percent` if needed; out of scope for v1, which uses a single window)
- `cancellation_notes` — TextField(blank=True) — operator-facing free text the API exposes for display alongside the policy

`null` on either fee component = "inherit from `GroupFinance`". Both null at every level = no fee (full refund). Currency is read from the booking, not duplicated here.

## `GroupFinance(AuditedModel)`

OneToOne with `PropertyGroup`. Same fields as `PropertyFinance`, **non-nullable with sensible defaults**. The group is the floor — every inheritable concern must resolve to a value at the group level.

- `group` — OneToOne PropertyGroup CASCADE primary_key
- All `commission_*`, `tax_*`, `bank_*`, `deposit_*` / `interim_*` / `days_*` (payment-schedule), `security_deposit_*`, and `cancellation_*` fields above, but required (with TextChoices defaults and 0 / empty-string defaults for amount / note fields where domain-sensible). The cancellation policy in particular must resolve to a value at group level — a portfolio with no group-level cancellation policy effectively offers full refunds, which should be a deliberate choice.

The `bank_account_*` block is the group's default payout account — overridden per property when a sub-portfolio uses a different one.

`GroupFinance` rows are created automatically with the `PropertyGroup` (`post_save` signal) and live for the group's lifetime. The API exposes them at `/property-groups/{id}/finance` (read/patch only; no POST/DELETE — see reconciliation issue #38).

## Resolver

On `PropertyFinance`:

```python
def effective_commission(self) -> dict:
    """Returns {calculation_type, amount, note} merged from property → group."""
    return {
        "calculation_type": self.commission_calculation_type
            or self.property.group.finance.commission_calculation_type,
        "amount": self.commission_amount
            if self.commission_amount is not None
            else self.property.group.finance.commission_amount,
        "note": self.commission_note or self.property.group.finance.commission_note,
    }

def effective_tax_policy(self) -> dict: ...
def effective_payment_schedule(self) -> dict: ...
def effective_security_deposit_policy(self) -> dict: ...
def effective_bank_account(self) -> dict: ...
```

Generic helper:

```python
def effective(self, field: str):
    own = getattr(self, field)
    if own is not None and own != "":
        return own
    return getattr(self.property.group.finance, field)
```

Pricing engine and booking flow call resolvers; nothing reads `getattr(finance, 'commission_amount')` directly.

## Lifecycle and audit history

Finance configuration is "current state", not a transactional log. Edits update the row in place.

- **No soft delete.** Per `00-conventions.md`, `PropertyFinance` and `GroupFinance` inherit from `AuditedModel` only. There is no `deleted_at` column, no hidden manager.
- **Hard delete cascades** from `Property` / `PropertyGroup` to the owning finance row when the parent is hard-deleted. ARCHIVED properties keep their finance row intact so historical reporting still resolves them.
- **Financial history reconstruction** is the responsibility of `Booking.pricing_snapshot`. That JSONField captures the commission %, tax %, surcharges, and Extras resolved at booking-creation time via the `PricingEngine`. Owner-statement and reconciliation reports read from snapshots, not by looking up "the commission rate as of date X" from a history table. The live `PropertyFinance.commission_amount` is always "current state".
- **"Who changed commission from 10% to 12%?"** is answered by `AuditLog` rows. The finance app calls `core.audit.track(PropertyFinance, fields=[...])` and `core.audit.track(GroupFinance, fields=[...])` in `apps.ready()`. A `pre_save` signal emits an `AuditLog` row keyed by content type + object id with `field_diffs` containing the before/after pair per changed field. Sensitive fields (`bank_account_number`, `bank_iban`, `bank_bic`, `bank_sort_code`) are tagged for redaction: the diff value is replaced with `"[REDACTED]"` before write, so the fact of the change is recorded without leaking the cleartext IBAN into the audit table. Encryption-at-rest on the live row continues to cover the PII concern.

## Why flat (not split)

- The legacy `VillaFinance` had ~30 columns mixing five concerns. An earlier draft of this design split them into five OneToOne children to allow per-concern permissions (e.g. `can_view_bank_account` separate from `can_view_commission`).
- That granularity isn't part of MVP. Staff roles (`ADMIN` / `RESERVATIONS` / `ACCOUNTS` / `VIEWER` per `01-accounts.md`) gate the whole finance form. The `ACCOUNTS` role sees everything finance-related; the `RESERVATIONS` role sees none of it; the `VIEWER` role sees a read-only view.
- One flat model means: one admin form, one serializer, one resolver helper, no five-way OneToOne join, no fanned-out migrations.
- Field-name prefixing (`commission_*`, `tax_*`, `bank_*`, `deposit_*`, `interim_*`, `security_deposit_*`) keeps the schema readable without `\d` requiring a join across five tables.
- If granular per-concern permissions ever land post-v1, splitting back out is a structural refactor that the resolver layer absorbs cleanly — callers go through `effective_commission()` / `effective_tax_policy()` / etc., not direct field access.

See reconciliation issue #36.

## Out of scope

- Bank-account secret encryption library choice — picked at implementation time.
- Tax jurisdictions beyond a single percentage / exempt flag (e.g. VAT vs occupancy tax) — current data model uses one rate; revisit when business demands.
- Owner payout / accounting ledger — separate `accounting` app, future scope.
