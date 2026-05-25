"""BookingService — create a Booking off an accepted QuotationLine."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from properties.services.changeover import ChangeoverService
from reservations.enums import PaymentMethod
from reservations.models.booking import Booking
from reservations.models.quotation import QuotationLine
from reservations.services.holds import HoldService


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
        allow_changeover_override: bool = False,
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
            return existing

        quotation = quotation_line.quotation
        property_ = quotation_line.property
        snapshot = dict(quotation_line.pricing_snapshot or {})

        # Re-validate changeover at confirmation: a quote can pre-date a new
        # ChangeOverRule. Skipped on the idempotent retry path above.
        ChangeoverService.validate_arrival(
            property_,
            quotation_line.date_from,
            allow_override=allow_changeover_override,
        )

        requires_pre_approval = cls._requires_pre_approval(property_)
        balance_due_at = property_.balance_due_at(quotation_line.date_from)
        total = cls._decimal(snapshot.get("total", quotation_line.total))

        booking = Booking.objects.create(
            quotation_line=quotation_line,
            guest=quotation.guest,
            property=property_,
            date_from=quotation_line.date_from,
            date_to=quotation_line.date_to,
            adults=quotation_line.adults,
            children=quotation_line.children,
            currency=quotation.currency,
            pricing_snapshot=snapshot,
            rental_price=cls._decimal(snapshot.get("rate_subtotal", 0)),
            balance_due=total,
            balance_due_at=balance_due_at,
            agent=agent,
            terms_version=terms_version,
            terms_accepted_at=timezone.now(),
            payment_method=payment_method,
        )

        # TODO: integrate with payments.PaymentScheduler.create_for_booking once
        # the payments app lands. For now the Booking just records the balance.

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
