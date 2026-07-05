"""Shared helpers used by the booking + payment seed stages.

Kept private to the seed package — these are not general-purpose service
calls, they are seeder-only glue around the production service layer.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

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


def conforming_stay(ctx: SeedContext, prop: Any, date_from: date, nights: int) -> tuple[date, date]:
    """Snap a candidate stay to the property's seeded stay rules.

    Advances `date_from` to the required changeover weekday (if any) and
    raises `nights` to the villa's minimum, so the pricing engine never has to
    silently `align_forward` a seeded stay or reject it with MinNightsNotMet.
    Unconstrained villas (and every villa when the knob is off — the rules map
    stays empty) pass through unchanged.
    """
    weekday, min_nights = ctx.property_stay_rules.get(prop.pk, (None, 1))
    nights = max(nights, min_nights)
    if weekday is not None:
        date_from += timedelta(days=(weekday - date_from.weekday()) % 7)
    return date_from, date_from + timedelta(days=nights)


def pick_guest(ctx: SeedContext) -> Any:
    """Pick a customer (Person) from the repeat pool with high probability,
    otherwise a fresh one. Empty pool always returns fresh."""

    from accounts.factories import CustomerPersonFactory

    if ctx.guest_pool and ctx.rng.random() < 0.6:
        return ctx.rng.choice(ctx.guest_pool)
    return CustomerPersonFactory()


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


def create_one_booking(
    ctx: SeedContext,
    prop: Any,
    *,
    date_from: date,
    date_to: date,
    i: int,
    terms: Any,
    expires_at: Any,
    force_occupying: bool = False,
) -> Any:
    """Build one Enquiry -> Quotation -> Booking for `prop` over the given dates.

    The single source of truth for opening a seeded booking, shared by the
    legacy round-robin path and the dense-calendar path so the two never drift.
    Always goes through the real service layer (the only path that satisfies the
    LEAD BookingGuest invariant).

    `force_occupying` leaves the booking in its initial non-terminal state
    (AWAITING_DEPOSIT, or PENDING_OWNER_APPROVAL on a pre-approval property) by
    skipping `advance_status`, so the cell stays `booked` and a back-to-back
    changeover day survives. Otherwise the booking is walked down its state
    machine for status variety.
    """
    from django.db import transaction

    from reservations.enums import BookingStatus, EnquiryStatus
    from reservations.factories import EnquiryFactory
    from reservations.models.enquiry import Enquiry
    from reservations.services.bookings import BookingService
    from reservations.services.quotations import QuotationService

    customer = pick_guest(ctx)
    enquiry = cast(
        Enquiry,
        EnquiryFactory(person=customer, property=prop, date_from=date_from, date_to=date_to),
    )
    ctx.enquiry_pks.append(enquiry.pk)
    with transaction.atomic():
        quotation = QuotationService.create_from_enquiry(
            enquiry,
            [
                {
                    "property": prop,
                    "date_from": date_from,
                    "date_to": date_to,
                    "adults": 2,
                    "children": 1,
                }
            ],
            terms_version=terms,
            expires_at=expires_at,
        )
        line = quotation.lines.first()
        if line is None:
            raise RuntimeError("QuotationService produced no lines")
        quotation.send()
        requires_pre_approval = bool(prop.settings.bookings_require_pre_approval)
        if not requires_pre_approval:
            quotation.accept(line)
        booking = BookingService.create_from_quotation_line(line, terms_version=terms)
        ctx.booking_pks.append(booking.pk)
        # Payments are scheduled by the `booking_transitioned` receiver in the
        # payments app the moment the booking reaches AWAITING_DEPOSIT (which
        # `create_from_quotation_line` triggers via auto_accept). The seeder no
        # longer schedules them by hand — seeded bookings now follow the exact
        # production path, so there is no seeded-vs-real divergence to drift.
        if not force_occupying:
            advance_status(booking, i, ctx)
        booking.refresh_from_db()
        if booking.status not in (
            BookingStatus.DECLINED.value,
            BookingStatus.PENDING_OWNER_APPROVAL.value,
        ):
            enquiry.refresh_from_db()
            # `Quotation.accept()` flips the parent enquiry to CONVERTED inside
            # its own atomic block, so only convert here if it hasn't already.
            if enquiry.status != EnquiryStatus.CONVERTED.value:
                enquiry.convert(quotation)
    return booking


def advance_pre_approval(booking: Any, i: int, ctx: SeedContext) -> None:
    from payments.enums import PaymentPurpose

    decline_threshold = int(ctx.knobs.pct_booking_pre_approval_declines * 100)
    if (i * 7) % 100 < decline_threshold:
        booking.owner_decline("Owner unavailable")
        return
    if i % 3 == 0:
        return  # leave PENDING_OWNER_APPROVAL
    booking.owner_approve()  # → AWAITING_DEPOSIT; the payments receiver schedules here
    line = booking.quotation_line
    line.quotation.accept(line)
    booking.record_deposit()
    mark_payment_paid(booking, PaymentPurpose.DEPOSIT.value)
