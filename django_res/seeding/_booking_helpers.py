"""Shared helpers used by the booking + payment seed stages.

Kept private to the seed package — these are not general-purpose service
calls, they are seeder-only glue around the production service layer.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from seeding.context import SeedContext


def next_stay_start(prop: Any, cursors: dict[int, date], ctx: SeedContext) -> date:
    """Return a sensible date_from for the next booking on `prop`.

    Honours `booking_date_spread_days`: distributes start dates across a
    symmetric window around today so dashboards see a populated calendar.
    Per-property cursor avoids overlap when multiple bookings land on the
    same villa.
    """

    spread = ctx.knobs.booking_date_spread_days
    if spread > 0 and prop.pk not in cursors:
        bucket = prop.pk % 8
        offset = int((bucket / 7) * 2 * spread - spread)
        return ctx.today + timedelta(days=offset)
    return cursors.get(prop.pk, ctx.today + timedelta(days=21))


def pick_guest(ctx: SeedContext) -> Any:
    """Pick a guest from the repeat pool with high probability, otherwise a
    fresh one. Empty pool always returns fresh."""

    from reservations.factories import GuestFactory

    if ctx.guest_pool and ctx.rng.random() < 0.6:
        return ctx.rng.choice(ctx.guest_pool)
    return GuestFactory()


def populate_payments(booking: Any) -> None:
    from payments.services.payment_scheduler import PaymentScheduler
    from payments.services.security_deposit import SecurityDepositService
    from reservations.enums import BookingStatus

    if booking.status == BookingStatus.PENDING_OWNER_APPROVAL.value:
        return
    PaymentScheduler.create_for_booking(booking)
    SecurityDepositService.create_for_booking(booking)


def mark_payment_paid(booking: Any, purpose: str) -> None:
    from payments.enums import PaymentMethod, PaymentStatus
    from payments.models.payment import Payment

    payment = (
        Payment.objects.filter(booking=booking, purpose=purpose, status=PaymentStatus.PENDING.value)
        .order_by("pk")
        .first()
    )
    if payment is None:
        return
    payment.mark_paid(
        amount=payment.amount,
        paid_at=datetime.now(UTC),
        method=PaymentMethod.CARD.value,
        reference=f"SEED-{payment.pk}",
    )


def advance_status(booking: Any, i: int, ctx: SeedContext) -> None:
    """Walk a fraction of bookings down the state machine so timelines vary."""

    from payments.enums import PaymentPurpose
    from reservations.enums import BookingStatus

    if booking.status == BookingStatus.PENDING_OWNER_APPROVAL.value:
        advance_pre_approval(booking, i, ctx)
        return

    if ctx.knobs.pct_booking_expires and (i * 13) % 100 < int(ctx.knobs.pct_booking_expires * 100):
        booking.expire()
        return

    track = i % 6
    if track == 0:
        return  # AWAITING_DEPOSIT
    if track == 5:
        booking.cancel("Guest changed plans")
        return
    booking.record_deposit()
    mark_payment_paid(booking, PaymentPurpose.DEPOSIT.value)
    if ctx.knobs.pct_booking_cancel_post_deposit and (i * 19) % 100 < int(
        ctx.knobs.pct_booking_cancel_post_deposit * 100
    ):
        booking.cancel("Plans changed after deposit")
        return
    if track == 1:
        return  # DEPOSIT_PAID
    booking.arm_balance()
    booking.record_balance()
    mark_payment_paid(booking, PaymentPurpose.BALANCE.value)
    if track == 2:
        return  # BALANCE_PAID
    booking.check_in()
    if track == 3:
        return  # CHECKED_IN
    booking.check_out()  # track == 4 -> CHECKED_OUT


def advance_pre_approval(booking: Any, i: int, ctx: SeedContext) -> None:
    from payments.enums import PaymentPurpose

    decline_threshold = int(ctx.knobs.pct_booking_pre_approval_declines * 100)
    if (i * 7) % 100 < decline_threshold:
        booking.owner_decline("Owner unavailable")
        return
    if i % 3 == 0:
        return  # leave PENDING_OWNER_APPROVAL
    booking.owner_approve()
    line = booking.quotation_line
    line.quotation.accept(line)
    populate_payments(booking)
    booking.record_deposit()
    mark_payment_paid(booking, PaymentPurpose.DEPOSIT.value)
