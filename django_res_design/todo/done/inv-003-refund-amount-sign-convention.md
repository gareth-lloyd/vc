> **✅ RESOLVED (2026-06-15)** — Problem: Questioned the Refund.amount sign convention. Fix: Closed: partition-by-purpose fixes the sign convention.
>
> _Original ticket preserved below for context._

# INV-003 — `Refund.amount` sign convention

- **Status:** ✅ **CLOSED** (2026-05-27 critique) — convention is
  **partition by `purpose`**, not signed sum. `payments/serializers/track.py`
  aggregates per `(booking, purpose)`; REFUND is its own purpose
  partition and never mixes into DEPOSIT/BALANCE `paid_amount`. No
  "subtract refunds" code path exists or is needed in the current track.
  If a future net-position ledger view is added, codify the rule then.
- **Severity:** Investigation
- **Source:** the 2026-05-26 data-model deep audit "What I'd
  want to investigate further" item 3

## Question

Refund rows in the unified ledger likely store **positive amounts with a
purpose tag**. Booking balance computation must subtract them.

- Where does the invariant live ("REFUND rows count negative")?
- Is it tested anywhere?
- Is it documented in `07-payments.md`?

## Suggested probe

```
rg -n "REFUND" django_res/payments/services/
rg -n "amount" django_res/payments/services/refund.py
```

Look for the balance-computation code path (likely on Booking) and
verify it walks `Payment.objects.filter(purpose=REFUND)` with the right
sign.

## Outcome

If the convention is implicit, codify it: either with a `signed_amount`
property on Payment, or with a CheckConstraint that locks REFUND amounts
to positive (and document the rule).
