# FG-015 — `Booking.cancel` leaves PENDING Payment rows live

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
