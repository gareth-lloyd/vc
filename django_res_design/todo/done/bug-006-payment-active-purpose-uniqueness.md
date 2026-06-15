> **✅ RESOLVED (2026-06-15)** — Problem: Payment.unique_active_payment_per_purpose only covered DEPOSIT/BALANCE, leaving other purposes unconstrained. Fix: Replaced it with three per-purpose constraints; a security-deposit hold is superseded by its capture.
>
> _Original ticket preserved below for context._

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

## Resolution

✅ Replaced the single `unique_active_payment_per_purpose` constraint with three
per-purpose `UniqueConstraint`s on `booking` (migration `payments/0003`):
`unique_active_deposit_per_booking`, `unique_active_balance_per_booking`,
`unique_active_security_deposit_per_booking`. Each conditions on
`status__in=ACTIVE_PAYMENT_STATUSES & purpose=<the one>`; CONCIERGE/REFUND stay
unconstrained (many-per-booking).

**SECURITY_DEPOSIT hold+capture reconciliation (decision: "capture supersedes
hold").** The pre-auth flow previously left *two* active SD `Payment`s on a
booking — the `hold()` authorisation (SUCCEEDED) and the `claim()` capture
(SUCCEEDED) — which both violated the new SD constraint and double-counted the
deposit on the ledger. `SecurityDepositService.claim()` (pre-auth path) now calls
`_supersede_active_hold()` first, transitioning the still-active hold Payment to
`CANCELLED` (kind `SUPERSEDED_BY_CAPTURE`, fires no payment signal) before minting
the capture row. Net: exactly one active SD row per booking, and the constraint
holds.

Tests (`payments/tests/test_payment_constraints.py`): second-active-row rejected
for each of DEPOSIT/BALANCE/SECURITY_DEPOSIT; many-active allowed for
CONCIERGE/REFUND; an inactive SD frees the slot; and a pinning test on
`ACTIVE_PAYMENT_STATUSES` membership so a new status forces a constraint review.
The existing SD pre-auth/claim tests still pass (the hold is retired silently).

## Dependencies

None.
