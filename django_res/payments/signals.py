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
import structlog

logger = structlog.get_logger(__name__)

# Fired by `Payment.mark_paid` and by the webhook pipeline once a Payment
# settles. `_advance_booking_on_payment_settled` (below — payments-side, since
# reservations may not import payments) dispatches to `Booking.record_deposit`
# or `Booking.record_balance` based on `payment.purpose`.
payment_succeeded = django.dispatch.Signal()

# Fired when a Payment reaches a terminal failure state.
payment_failed = django.dispatch.Signal()

# Fired when a `Payment(purpose=REFUND)` reaches SUCCEEDED. Used by
# `RefundService` to advance the parent Refund and by reservations to update
# booking-level totals.
payment_refunded = django.dispatch.Signal()

# Fired by `Payment.waive`. Treated the same as `payment_succeeded` for
# booking-state advancement (no money has moved).
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


def _resync_schedule_on_booking_total_changed(
    sender: Any,
    *,
    booking: Any,
    **_: Any,
) -> None:
    """Resize the unsettled schedule when staff-entered money moves the total.

    reservations fires `booking_total_changed` from the charge-item model
    signals; the resize lives here because the spine forbids reservations →
    payments. The resync is a no-op until a schedule exists, and the
    charge-item write paths run inside one transaction with it, so the
    charge and the resized rows commit (or roll back) together.
    """
    from payments.services.payment_scheduler import PaymentScheduler

    PaymentScheduler.resync_for_booking(booking)


def _advance_booking_on_payment_settled(sender: Any, *, payment: Any, **_: Any) -> None:
    """Advance the Booking when a rental payment settles (or is waived).

    DEPOSIT → `Booking.record_deposit`; BALANCE → `Booking.record_balance`;
    every other purpose is not a rental-lifecycle payment and is ignored.

    Defensive by design: an `InvalidTransition` is logged and swallowed, never
    raised. That one mechanism covers double settlement (booking already
    advanced), seeding (which calls `record_*` before `mark_paid`), money
    landing on a cancelled/expired booking, and a balance settling while the
    booking is still AWAITING_DEPOSIT — in each case the settle itself must
    stand and ops resolves from the warning. Anything *other* than
    `InvalidTransition` propagates and rolls back the payment transition
    (`transition_to` dispatches inside its atomic block).
    """
    from core.exceptions import InvalidTransition
    from payments.enums import PaymentPurpose

    if payment.purpose == PaymentPurpose.DEPOSIT.value:
        advance = payment.booking.record_deposit
    elif payment.purpose == PaymentPurpose.BALANCE.value:
        advance = payment.booking.record_balance
    else:
        return

    try:
        advance(payment)
    except InvalidTransition:
        logger.warning(
            "payment.booking_advance_skipped",
            payment_id=payment.pk,
            booking_id=payment.booking_id,
            purpose=payment.purpose,
            booking_status=payment.booking.status,
            reason="invalid_transition",
        )


def _expire_payments_on_booking_expired(
    sender: Any,
    *,
    booking: Any,
    **_: Any,
) -> None:
    """Expire a booking's leftover PENDING payments when the booking expires.

    `reservations.tasks.expire_bookings` ages out AWAITING_DEPOSIT bookings;
    their unpaid DEPOSIT/BALANCE rows must follow, both to keep the ledger
    honest and to free the active-per-purpose constraint slots. Lives here
    (not in reservations) because the spine forbids reservations → payments.
    """
    from reservations.enums import BookingStatus

    if booking.status != BookingStatus.EXPIRED.value:
        return

    from payments.enums import EventSource, PaymentPurpose, PaymentStatus
    from payments.models.payment import Payment

    pending = Payment.objects.filter(
        booking=booking,
        status=PaymentStatus.PENDING.value,
        purpose__in=(
            PaymentPurpose.DEPOSIT.value,
            PaymentPurpose.BALANCE.value,
        ),
    )
    for payment in pending:
        payment.transition_to(
            PaymentStatus.EXPIRED.value,
            source=EventSource.SYSTEM.value,
            kind="BOOKING_EXPIRED",
        )


def _sync_refund_on_outbound_payment(sender: Any, *, payment: Any, **_: Any) -> None:
    """Advance the parent Refund when its outbound Payment terminates.

    Guarded to `Payment(purpose=REFUND)` rows carrying `meta['refund_id']`:
    `payment_refunded` also fires when an ordinary inbound payment reaches
    REFUNDED, and `payment_failed` fires for every purpose — neither of
    those has a Refund row to sync.
    """
    from payments.enums import PaymentPurpose

    if payment.purpose != PaymentPurpose.REFUND.value:
        return
    if not payment.meta.get("refund_id"):
        return

    from payments.services.refund import RefundService

    RefundService.sync_from_outbound_payment(payment)


def _register() -> None:
    """Connect the payments receivers to upstream domain signals.

    Called from `PaymentsConfig.ready()`. Payments fires its own signals for
    other apps to consume; it registers receivers here on its own signals and
    listens *down* the spine to reservations' `booking_transitioned`.
    """
    from reservations.signals import booking_total_changed, booking_transitioned

    booking_transitioned.connect(
        _schedule_payments_on_booking_confirmed,
        dispatch_uid="payments.schedule_on_booking_confirmed",
    )
    booking_total_changed.connect(
        _resync_schedule_on_booking_total_changed,
        dispatch_uid="payments.resync_on_booking_total_changed",
    )
    booking_transitioned.connect(
        _expire_payments_on_booking_expired,
        dispatch_uid="payments.expire_payments_on_booking_expired",
    )
    payment_succeeded.connect(
        _advance_booking_on_payment_settled,
        dispatch_uid="payments.advance_booking_on_payment_succeeded",
    )
    payment_waived.connect(
        _advance_booking_on_payment_settled,
        dispatch_uid="payments.advance_booking_on_payment_waived",
    )
    payment_refunded.connect(
        _sync_refund_on_outbound_payment,
        dispatch_uid="payments.sync_refund_on_payment_refunded",
    )
    payment_failed.connect(
        _sync_refund_on_outbound_payment,
        dispatch_uid="payments.sync_refund_on_payment_failed",
    )
