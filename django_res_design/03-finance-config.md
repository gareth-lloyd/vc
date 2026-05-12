# 03 — Property Finance Configuration

Splits the legacy `VillaFinance` god object (commission + tax + bank account + payment schedule + security deposit, all in one wide row) into focused models. Lives inside the `properties` app under `models/finance.py`.

## Approach

- One anchor model — `PropertyFinance` — OneToOne with Property.
- Five child models hanging off it as OneToOnes, one per concern.
- Each child mirrors at group level (`GroupCommission`, `GroupTaxPolicy`, etc.) on `PropertyGroup`.
- **Inheritance via null fields**: leave a value `NULL` on the property-level model to fall back to the group's value. The `effective_*()` resolver on `PropertyFinance` does the merge.

## Anchor

### `PropertyFinance(AuditedModel)`
- `property` — OneToOne Property CASCADE primary_key
- `season` — FK `pricing.RatePlan` SET_NULL, null=True (legacy `SeasonId`; ties finance to a rate plan in rare cases)
- `contact` — FK accounts.Contact PROTECT, null=True — financial recipient (owner who gets paid)
- `parent` — self-FK null=True (legacy `ParentId`; allows finance overrides for a sub-period referencing a parent finance config)
- `notes` — TextField(blank=True)

Reverse:
- `commission` (OneToOne Commission)
- `tax_policy` (OneToOne TaxPolicy)
- `bank_account` (OneToOne BankAccount)
- `payment_schedule` (OneToOne PaymentSchedule)
- `security_deposit_policy` (OneToOne SecurityDepositPolicy)

## Children

### `Commission(AuditedModel)`
- `finance` — OneToOne PropertyFinance CASCADE primary_key
- `calculation_type` — TextChoices (`PERCENT`, `FIXED`), null=True
- `amount` — DecimalField(12, 2, null=True, blank=True)
- `note` — TextField(blank=True)

### `TaxPolicy(AuditedModel)`
- `finance` — OneToOne primary_key
- `tax_number` — CharField(blank=True)
- `is_exempt` — BooleanField(null=True)
- `percentage` — DecimalField(5, 2, null=True, blank=True)  # e.g. 20.00 = 20%

`null` `is_exempt` and `null` percentage → inherit from group / country default.

### `BankAccount(AuditedModel)`
- `finance` — OneToOne primary_key
- `account_name` — CharField(blank=True)
- `account_number` — CharField(blank=True)
- `sort_code` — CharField(blank=True)
- `iban` — CharField(blank=True)
- `bic` — CharField(blank=True)
- `bank_name` — CharField(blank=True)
- `bank_address_line_1`, `bank_address_line_2`, `bank_post_code`, `bank_city` — CharField(blank=True)

Encrypt at rest if PII/secrets policy demands (app-layer Fernet wrap on save).

### `PaymentSchedule(AuditedModel)`
- `finance` — OneToOne primary_key
- `deposit_required` — BooleanField(null=True)
- `deposit_calculation_type` — TextChoices (`PERCENT`, `FIXED`), null=True
- `deposit_amount` — Decimal(12, 2, null=True, blank=True)
- `interim_required` — BooleanField(null=True)
- `interim_calculation_type` — TextChoices, null=True
- `interim_amount` — Decimal, null=True
- `days_interim_due_before_arrival` — PositiveSmallInteger(null=True)
- `days_balance_due_before_arrival` — PositiveSmallInteger(null=True)

Used by `payments.PaymentScheduler` to derive due dates at booking-creation time.

### `SecurityDepositPolicy(AuditedModel)`
- `finance` — OneToOne primary_key
- `is_required` — BooleanField(null=True)
- `amount_calculation_type` — TextChoices (`PERCENT`, `FIXED`), null=True
- `amount` — Decimal(12, 2, null=True)
- `calculate_from` — TextChoices (`NIGHTLY`, `WEEKLY`, `TOTAL_STAY`), null=True
- `days_due_before_arrival` — PositiveSmallInteger(null=True)
- `days_refunded_after_departure` — PositiveSmallInteger(null=True)
- `payment_method` — TextChoices (`CARD_HOLD`, `CARD_CHARGE`, `BANK_TRANSFER`), null=True

## Group-level mirrors

Each child has a `Group*` sibling on PropertyGroup. Same fields, **non-nullable with sensible defaults** — the group is the floor.

- `GroupCommission(AuditedModel)` — `group` OneToOne PropertyGroup CASCADE primary_key + same fields, required
- `GroupTaxPolicy(AuditedModel)` — same
- `GroupBankAccount(AuditedModel)` — same (the group's default payout account, can be overridden per property)
- `GroupPaymentSchedule(AuditedModel)` — same
- `GroupSecurityDepositPolicy(AuditedModel)` — same

## Resolver

On `PropertyFinance`:

```python
def effective_commission(self) -> Commission:
    # Returns a dataclass/dict with each field resolved
    # by precedence: property.commission -> group.commission
    ...
```

Or generic helper:

```python
def effective(self, child_name: str, field: str):
    own = getattr(getattr(self, child_name, None), field, None)
    if own is not None:
        return own
    group = self.property.group
    return getattr(getattr(group, child_name), field)
```

Pricing engine and booking flow call resolvers; nothing reads `getattr(finance.commission, 'amount')` directly.

## Lifecycle and audit history

Finance configuration is "current state", not a transactional log. Edits update each row in place.

- **No soft delete.** Per `00-conventions.md`, `PropertyFinance` and its OneToOne children inherit from `AuditedModel` only. There is no `deleted_at` column, no hidden manager.
- **Hard delete cascades** from `PropertyFinance` to its five children when a property's finance setup is dismantled. Group-level finance siblings CASCADE from `PropertyGroup`. In practice this only happens when the property itself is hard-deleted; ARCHIVED properties keep their finance rows intact so historical reporting still resolves them.
- **Financial history reconstruction** is the responsibility of `Booking.pricing_snapshot`. That JSONField captures the commission %, tax %, surcharges, and Extras resolved at booking-creation time via the `PricingEngine`. Owner-statement and reconciliation reports read from snapshots, not by looking up "the commission rate as of date X" from a history table. The live `PropertyFinance.Commission.amount` is always "current state".
- **"Who changed commission from 10% to 12%?"** is answered by `AuditLog` rows. The finance app calls `core.audit.track(Commission, fields=["calculation_type", "amount", "note"])` in `apps.ready()`; the same for `TaxPolicy`, `PaymentSchedule`, `SecurityDepositPolicy`, and `BankAccount`. A `pre_save` signal emits an `AuditLog` row keyed by content type + object id with `field_diffs` containing the before/after pair per changed field. Sensitive fields on `BankAccount` (`account_number`, `iban`, `bic`, `sort_code`) are tagged for redaction: the diff value is replaced with `"[REDACTED]"` before write, so the fact of the change is recorded without leaking the cleartext IBAN into the audit table. Encryption-at-rest on the live row continues to cover the PII concern.

## Why split

- The legacy `VillaFinance` had ~30 columns mixing five concerns. A single admin form for "edit finance" became a 30-field god-form.
- Splitting into five OneToOnes lets admin inlines each form one concern, with its own permissions (e.g. `can_view_bank_account` separate from `can_view_commission`).
- Validation tightens: bank account `clean()` can require IBAN if BIC is set, without polluting commission validation.
- Schema discovery improves: `\d properties_commission` tells you the commission shape immediately.

## Out of scope

- Bank-account secret encryption library choice — picked at implementation time.
- Tax jurisdictions beyond a single percentage / exempt flag (e.g. VAT vs occupancy tax) — current data model uses one rate; revisit when business demands.
- Owner payout / accounting ledger — separate `accounting` app, future scope.
