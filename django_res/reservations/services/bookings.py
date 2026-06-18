"""BookingService — create a Booking off an accepted QuotationLine."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog
from django.db import transaction
from django.utils import timezone

from core.exceptions import TerminalBookingExists
from reservations.enums import TERMINAL_BOOKING_STATUSES, BookingGuestRole, PaymentMethod
from reservations.models.booking import Booking
from reservations.models.booking_guest import BookingGuest
from reservations.models.quotation import QuotationLine
from reservations.services.holds import HoldService

logger = structlog.get_logger(__name__)


class BookingService:
    """Create + initialise Booking rows."""

    @classmethod
    @transaction.atomic
    def create_from_quotation_line(
        cls,
        quotation_line: QuotationLine,
        terms_version: Any,
        payment_method: str = PaymentMethod.CARD.value,
        *,
        agent: Any = None,
        actor: Any = None,
    ) -> Booking:
        """Copy the line's pricing snapshot, build a Booking, release holds.

        Idempotent on `quotation_line`: a `QuotationLine` represents a
        single guest commitment, so a retry from the same accept-quotation
        webhook (or a double-clicked staff UI) returns the existing
        Booking instead of opening a second one. The hold release and
        initial transition are skipped in that case — both ran on the
        first call.

        The booking is created in DRAFT and immediately driven through
        either `booking.auto_accept()` or `booking.submit()` so the
        `booking_transitioned` signal fires for the initial step and a
        single `BookingEvent` row is written by `Booking._transition`.
        """
        existing = Booking.objects.filter(quotation_line=quotation_line).first()
        if existing is not None:
            # The retry contract only covers a live booking. Serving a
            # CANCELLED/EXPIRED/DECLINED one back as a fresh success would
            # resurrect a closed commitment — re-book via a new quotation.
            if existing.status in TERMINAL_BOOKING_STATUSES:
                raise TerminalBookingExists(
                    f"Booking {existing.reference} for this quotation line is "
                    f"{existing.status}; re-book via a new quotation."
                )
            return existing

        quotation = quotation_line.quotation
        property_ = quotation_line.property
        snapshot = dict(quotation_line.pricing_snapshot or {})

        # Quoting no longer auto-holds its dates, so another party may have
        # held the villa between quote and accept. Refuse to book over a
        # foreign live hold; the quotation's own line holds are excluded so
        # they never block their own conversion. Booking-vs-booking overlap
        # is still enforced by the Booking EXCLUDE constraint.
        HoldService.assert_no_foreign_hold(
            property=property_,
            date_from=quotation_line.date_from,
            date_to=quotation_line.date_to,
            quotation=quotation,
        )

        # The booking inherits the line's dates verbatim. Any changeover shift
        # already happened at pricing time and was persisted onto the line
        # (GAP-007), so there is nothing to re-validate or re-align here.
        requires_pre_approval = cls._requires_pre_approval(property_)
        balance_due_at = property_.balance_due_at(quotation_line.date_from)
        total = cls._decimal(snapshot.get("total", quotation_line.total))

        # GAP-045 Unit 3d-A: `Quotation.person` is now the authoritative,
        # NOT-NULL customer FK, so read it directly (one fewer query than
        # re-resolving from the now-nullable guest leg) and set it on both the
        # Booking and its LEAD BookingGuest below, in lockstep with the Guest FK.
        person = quotation.person
        booking = Booking.objects.create(
            quotation_line=quotation_line,
            guest=quotation.guest,
            person=person,
            property=property_,
            date_from=quotation_line.date_from,
            date_to=quotation_line.date_to,
            adults=quotation_line.adults,
            children=quotation_line.children,
            # The line's currency, not a header one — the booking prices in
            # whatever the accepted option was priced in (GAP-014 / FG-001).
            currency=quotation_line.currency,
            pricing_snapshot=snapshot,
            rental_price=cls._decimal(snapshot.get("rate_subtotal", 0)),
            balance_due=total,
            balance_due_at=balance_due_at,
            agent=agent,
            terms_version=terms_version,
            terms_accepted_at=timezone.now(),
            payment_method=payment_method,
        )

        # Birth the LEAD `BookingGuest` row alongside the Booking. The
        # quotation's guest is the lead by definition — that is who accepted
        # the quote. Creating the row inside the same `transaction.atomic()`
        # keeps Booking + LEAD an indivisible pair: if either insert fails
        # both roll back, preserving the "every Booking has exactly one LEAD"
        # invariant the partial-unique constraint and pre_delete guard rely
        # on. `Booking.guest` is already set above; the post_save sync signal
        # is idempotent (it excludes rows that already match), so the second
        # write is a no-op.
        BookingGuest.objects.create(
            booking=booking,
            guest=quotation.guest,
            person=person,
            role=BookingGuestRole.LEAD.value,
        )

        # Payments are scheduled out-of-band: the `auto_accept`/`submit`
        # transition below fires `booking_transitioned`, which a payments-side
        # receiver consumes to call `PaymentScheduler.create_for_booking` once
        # the booking reaches AWAITING_DEPOSIT. `reservations` must not import
        # `payments` directly (it sits below it in the import spine), so the
        # signal is the seam — see `payments/signals.py`.

        # Release competing holds for this property/date_range that we don't own.
        HoldService.release_for_quotation(quotation)

        transition_meta = {"quotation_line_id": quotation_line.pk}
        if requires_pre_approval:
            booking.submit(
                actor=actor,
                reason="Created from quotation line",
                meta=transition_meta,
            )
        else:
            booking.auto_accept(
                actor=actor,
                reason="Created from quotation line",
                meta=transition_meta,
            )

        logger.info(
            "booking.created",
            booking_id=booking.pk,
            reference=booking.reference,
            property_id=property_.pk,
            quotation_line_id=quotation_line.pk,
            requires_pre_approval=requires_pre_approval,
            booking_status=booking.status,
        )
        return booking

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        return Decimal(str(value)).quantize(Decimal("0.01"))

    @staticmethod
    def _requires_pre_approval(property_: Any) -> bool:
        settings_obj = getattr(property_, "settings", None)
        if settings_obj is None:
            return False
        resolver = getattr(settings_obj, "effective", None)
        if resolver is None:
            return False
        try:
            return bool(resolver("bookings_require_pre_approval"))
        except AttributeError:
            return False
