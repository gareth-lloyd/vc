# FG-004 — `Payment` fields aren't gated by `purpose`

> **✅ RESOLVED (2026-06-04).** Three `CheckConstraint`s added to
> `Payment.Meta` (migration `payments/0004`):
> `payment_refund_has_no_due_at`,
> `payment_concierge_item_only_for_concierge`, and
> `payment_refund_amount_non_negative` (INV-003 positive-amount
> convention, REFUND-scoped — ADJUSTMENT left unconstrained pending its
> design). Tests in `payments/tests/test_payment_constraints.py`.
> The signed-amount convention for non-REFUND purposes was deliberately
> left out of scope.

- **Severity:** 🟠 Footgun
- **Source:** the 2026-05-26 data-model deep audit §F4
- **Files:** `payments/models/payment.py:39–110`

## Problem

Single-table polymorphism: every row carries every field even when the
field is meaningless for that `purpose`.

- `due_at` only makes sense for forward-looking purposes (DEPOSIT,
  BALANCE, SECURITY_DEPOSIT). A `REFUND` row with `due_at` set is
  nonsense.
- `concierge_item` (if present) only applies when `purpose=CONCIERGE`.
- A `REFUND` row's `amount` is conceptually negative; sign convention
  lives in code, not in a constraint.

## Proposed fix

Add per-purpose `CheckConstraint`s, e.g.

```python
CheckConstraint(
    condition=~(Q(purpose=PaymentPurpose.REFUND.value) & Q(due_at__isnull=False)),
    name="payment_refund_has_no_due_at",
)
CheckConstraint(
    condition=Q(purpose=PaymentPurpose.CONCIERGE.value) | Q(concierge_item__isnull=True),
    name="payment_concierge_item_only_for_concierge",
)
```

For `REFUND.amount` sign: pick a convention (positive amount + purpose
tag is probably best — the unified ledger sums signed by `purpose`) and
add a CheckConstraint that locks it in.

## Acceptance

- Constraints landed for each invariant.
- Tests asserting `IntegrityError` on each bad shape.

## Dependencies

Should follow [BUG-006](bug-006-payment-active-purpose-uniqueness.md) so
the constraint set on `Payment` is shaped once and consistently.
