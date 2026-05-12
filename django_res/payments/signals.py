"""Payments app signals.

These are the public side of the contract documented in `07-payments.md`.
The `reservations`, `comms`, and reporting apps register receivers on these
signals — `payments` itself only fires them inside transition methods.
"""

from __future__ import annotations

import django.dispatch

# Fired by `Payment.mark_paid` and by the webhook pipeline once a Payment
# settles. Receiver in reservations dispatches to `Booking.record_deposit` or
# `Booking.record_balance` based on `payment.purpose`.
payment_succeeded = django.dispatch.Signal()

# Fired when a Payment reaches a terminal failure state.
payment_failed = django.dispatch.Signal()

# Fired when a `Payment(purpose=REFUND)` reaches SUCCEEDED. Used by
# `RefundService` to advance the parent Refund and by reservations to update
# booking-level totals.
payment_refunded = django.dispatch.Signal()

# Fired by `Payment.waive`. Reservations treats this the same as
# `payment_succeeded` for booking-state advancement (no money has moved).
payment_waived = django.dispatch.Signal()

# Fired when a SecurityDeposit reaches a release-style terminal state.
security_deposit_released = django.dispatch.Signal()

# Fired when a SecurityDeposit auto-expires (gateway voided the hold).
security_deposit_expired = django.dispatch.Signal()


def _register() -> None:
    """No receivers wired inside the payments app itself.

    Cross-app receivers register in their own `apps.ready()`. The function
    exists so `apps.py:ready()` can import this module unambiguously.
    """
