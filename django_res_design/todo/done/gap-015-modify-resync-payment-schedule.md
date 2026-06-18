> **✅ RESOLVED (2026-06-18)** — Problem: `modify_dates`/`modify_guests`
> re-priced the booking but left the deposit/balance schedule stale. Fix: both
> methods now fire `booking_total_changed` (via a `_resync_payment_schedule`
> helper) inside their atomic block, reusing the charge-item resync chain so
> reservations stays off the payments import. Acceptance pinned by four tests in
> `reservations/tests/test_booking.py` (pricier range resizes both rows; settled
> deposit untouched while balance absorbs; all-settled writes the residual event;
> modify_guests fires the signal). Commit: dff1a54.
>
> _Original ticket preserved below for context._

# GAP-015 — `modify_dates` / `modify_guests` don't resync the payment schedule

- **Severity:** Gap
- **Source:** booking-charge-items work (2026-06-10)
- **Files:** `django_res/reservations/models/booking.py` (`modify_dates`,
  `modify_guests`), `django_res/payments/services/payment_scheduler.py`

## Problem

`PaymentScheduler.resync_for_booking` now resizes unsettled DEPOSIT/BALANCE
rows whenever staff-entered charge items move the booking total. But the two
existing modify endpoints — which re-run the pricing engine and rewrite
`balance_due` — still leave the schedule untouched, exactly the stale-schedule
behaviour the resync was built to fix. Legacy regenerated the schedule on
*every* booking modify.

Deliberately not wired during the charge-items phase: it changes the
observable behaviour of two existing endpoints, which deserves its own
review + tests.

## Proposed fix

Send `booking_total_changed` (or call the resync via the signal) at the end of
`modify_dates` / `modify_guests`, inside the same `transaction.atomic` block —
a ~2-line change now that `resync_for_booking` exists. Tests: modify dates onto
a pricier range → PENDING balance grows; deposit already SUCCEEDED → only
balance resized; residual path writes the `payment_schedule_residual` event.
