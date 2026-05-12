"""BookingService — create a Booking off an accepted QuotationLine."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from reservations.enums import BookingStatus, EventSource, PaymentMethod
from reservations.models.booking import Booking, BookingEvent
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
    ) -> Booking:
        """Copy the line's pricing snapshot, build a Booking, release holds."""
        quotation = quotation_line.quotation
        property_ = quotation_line.property
        snapshot = dict(quotation_line.pricing_snapshot or {})

        # Initial status: PENDING_OWNER_APPROVAL if the property requires pre-approval.
        requires_pre_approval = cls._requires_pre_approval(property_)
        initial_status = (
            BookingStatus.PENDING_OWNER_APPROVAL.value
            if requires_pre_approval
            else BookingStatus.AWAITING_DEPOSIT.value
        )

        balance_due_at = cls._compute_balance_due_at(property_, quotation_line.date_from)
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
            status=initial_status,
            agent=agent,
            terms_version=terms_version,
            terms_accepted_at=timezone.now(),
            payment_method=payment_method,
        )

        # TODO: integrate with payments.PaymentScheduler.create_for_booking once
        # the payments app lands. For now the Booking just records the balance.

        # Release competing holds for this property/date_range that we don't own.
        HoldService.release_for_quotation(quotation)

        BookingEvent.objects.create(
            booking=booking,
            from_status=BookingStatus.DRAFT.value,
            to_status=initial_status,
            actor=actor,
            source=EventSource.SYSTEM.value,
            reason="Created from quotation line",
            meta={"quotation_line_id": quotation_line.pk},
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

    @staticmethod
    def _compute_balance_due_at(property_: Any, date_from: Any) -> Any:
        """Derive `balance_due_at` from the property's effective payment schedule."""
        finance = getattr(property_, "finance", None)
        if finance is None:
            return None
        try:
            schedule = finance.effective_payment_schedule()
        except AttributeError:
            return None
        days_before = schedule.get("days_balance_due_before_arrival")
        if days_before is None:
            return None
        return date_from - timedelta(days=int(days_before))
