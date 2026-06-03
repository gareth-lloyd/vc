"""Payments app signals.

These are the public side of the contract documented in `07-payments.md`.
The `reservations`, `comms`, and reporting apps register receivers on these
signals — `payments` itself only fires them inside transition methods.

`payments` also *consumes* one upstream signal: it listens to reservations'
`booking_transitioned` to schedule a booking's payments the moment it lands in
AWAITING_DEPOSIT (see `_schedule_payments_on_booking_confirmed`). Because
`payments` sits above `reservations` in the import spine, a payments-side
receiver on a reservations signal is a clean downward edge — `reservations`
must never import `payments` to do this itself.
"""

from __future__ import annotations

from typing import Any

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


def _schedule_payments_on_booking_confirmed(
    sender: Any,
    *,
    booking: Any,
    to_status: str,
    **_: Any,
) -> None:
    """Schedule a booking's payments once it reaches AWAITING_DEPOSIT.

    Both entry paths converge here: `Booking.auto_accept` (DRAFT →
    AWAITING_DEPOSIT) and `Booking.owner_approve` (PENDING_OWNER_APPROVAL →
    AWAITING_DEPOSIT). The scheduler is idempotent (keyed on the booking), so a
    booking that re-enters AWAITING_DEPOSIT does not double-schedule, and a
    property without a finance row schedules nothing rather than raising.

    `booking_transitioned` is dispatched *after* `Booking._transition`'s own
    atomic block commits, so atomicity of "status changed ⇔ payments scheduled"
    depends on the caller wrapping the transition in a transaction. The in-app
    entry points do: `BookingService.create_from_quotation_line` is
    `@transaction.atomic`, and the owner-approve view wraps `owner_approve()` in
    `transaction.atomic`. Under those callers a scheduling failure rolls the
    whole transition back, keeping booking and payments an indivisible pair. A
    caller that drives the transition outside a transaction would commit the
    status change before this receiver runs — don't do that.
    """
    from reservations.enums import BookingStatus

    if to_status != BookingStatus.AWAITING_DEPOSIT.value:
        return

    # Local import: keep `payments.signals` importable at app-load without
    # pulling the service graph (which reaches into models) too early.
    from payments.services.payment_scheduler import PaymentScheduler

    # Schedules deposit + balance and, internally, the SecurityDeposit row.
    PaymentScheduler.create_for_booking(booking)


def _register() -> None:
    """Connect the payments receivers to upstream domain signals.

    Called from `PaymentsConfig.ready()`. Payments fires its own signals for
    other apps to consume; the one receiver it registers here listens *down*
    the spine to reservations' `booking_transitioned`.
    """
    from reservations.signals import booking_transitioned

    booking_transitioned.connect(
        _schedule_payments_on_booking_confirmed,
        dispatch_uid="payments.schedule_on_booking_confirmed",
    )
