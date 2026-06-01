# BUG-006 — `Payment.unique_active_payment_per_purpose` covers only DEPOSIT + BALANCE

- **Severity:** 🔴 Bug
- **Source:** the 2026-05-26 data-model deep audit §B6
- **Files:** `payments/models/payment.py:98–110`,
  `payments/enums.py:33` (`ACTIVE_PAYMENT_STATUSES`)

## Problem

The constraint name implies a general rule but the `condition` only
covers `DEPOSIT` and `BALANCE`. Two active `SECURITY_DEPOSIT` rows for the
same booking are allowed today, as are two active `CONCIERGE` rows. SD is
the dangerous one — duplicate active SDs mean two real holds on the
guest's card.

Secondary issue: the constraint depends on the Python tuple
`ACTIVE_PAYMENT_STATUSES`. Adding a new status (e.g. `AUTHORISED`)
silently weakens the constraint unless someone remembers to update the
tuple **and** generate a migration that rewrites the constraint.

## Proposed fix

Decide per-purpose cardinality explicitly:

| Purpose | Active cardinality |
|---|---|
| `DEPOSIT` | 1 per booking |
| `BALANCE` | 1 per booking |
| `SECURITY_DEPOSIT` | 1 per booking |
| `CONCIERGE` | many (one per item) |
| `REFUND` | many (one per source payment) |

Replace the single constraint with three named constraints, one per
single-cardinality purpose. Drop the `purpose__in` filter from the
condition so the rule reads cleanly.

For the enum-drift issue: pin `ACTIVE_PAYMENT_STATUSES` membership via a
test that asserts the current set, so adding a new status without
updating the constraint is a CI failure.

## Acceptance

- Three `UniqueConstraint`s (DEPOSIT, BALANCE, SECURITY_DEPOSIT) +
  migration.
- Test asserting `IntegrityError` on a second active SD per booking.
- Test pinning `ACTIVE_PAYMENT_STATUSES` so additions force a constraint
  review.

## Dependencies

None.
