# FG-015 — `Booking.cancel` leaves PENDING Payment rows live

> **Resolved (2026-06-12).** Landed as `_close_money_on_booking_closed` in
> `payments/signals.py` (commit `0f39bfb`), registered in `_register()` with
> `dispatch_uid="payments.close_money_on_booking_closed"` on
> `booking_transitioned`. CANCELLED / DECLINED close PENDING DEPOSIT/BALANCE
> rows as CANCELLED, EXPIRED as EXPIRED, each with a `BOOKING_*`
> `PaymentEvent`; settled money is never touched (refunds stay a manual
> operator workflow). PROCESSING rows are left to resolve via webhook — the
> warning fires later as `payment.booking_advance_skipped` when the settle
> lands on the closed booking, rather than at cancel time as proposed here.
> A money-holding SecurityDeposit is flagged via `payment.sd_review_required`
> instead of auto-released; an empty one (AWAITING_*) closes as FAILED.
> Acceptance pinned by `payments/tests/test_booking_terminal_money.py`
> (including `test_cancel_frees_per_purpose_constraint_slot` for the freed
> per-purpose slot) and
> `test_payment_reminders.py::test_terminal_booking_does_not_get_reminder`.

- **Severity:** 🟠 Footgun
- **Source:** the 2026-06-10 backend general review (consistency / architecture / stability)
- **Files:** `reservations/models/booking.py:426–443`, `payments/signals.py`

## Problem

`Booking.cancel` only flips the booking:

```python
return self._transition(
    allowed,
    BookingStatus.CANCELLED.value,
    ...
    extra_updates={"cancelled_at": timezone.now(), "cancel_reason": reason},
)
```

The booking's PENDING `DEPOSIT`/`BALANCE` Payment rows (scheduled at
confirmation by `_schedule_payments_on_booking_confirmed`) stay live: they
keep occupying the active-per-purpose unique-constraint slots (BUG-006's
constraints treat PENDING as active), keep matching due/reminder queries in
`payments/tasks.py`, and a later re-book of the same line can collide with
the stale rows.

## Proposed fix

Add a payments-side receiver on `reservations.signals.booking_transitioned`
for terminal transitions (CANCELLED, and EXPIRED where the beat task hasn't
already done it) that transitions the booking's PENDING payments to
CANCELLED/EXPIRED — the structural mirror of
`_advance_booking_on_payment_settled` (`payments/signals.py:87`), registered
in `_register()` with a `dispatch_uid`. Leave PROCESSING rows alone (in
flight at the gateway — they resolve via webhook) and log a warning when one
exists on a cancelled booking.

## Acceptance

- Test: cancelling an AWAITING_DEPOSIT booking leaves its PENDING payments
  CANCELLED and frees the per-purpose constraint slot (a new payment for a
  re-booked line can be created).
- Reminder task tests: cancelled bookings' payments no longer surface.

## Dependencies

Depends on the `PAYMENT_ALLOWED_TRANSITIONS` state guard and the
`expire_bookings` beat task landing on the feat/backend-review-fixes branch
(PENDING → CANCELLED/EXPIRED must be in the allowed map; the expiry task
already handles the EXPIRED half there).
