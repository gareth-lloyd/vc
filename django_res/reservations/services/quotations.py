"""QuotationService — build a Quotation+lines from an Enquiry, place holds."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypedDict

from django.db import transaction

from pricing.services import PricingEngine
from properties.services.changeover import ChangeoverService
from reservations.enums import BookingHoldReason, EnquiryStatus
from reservations.models.quotation import Quotation, QuotationLine
from reservations.services.holds import HoldService

if TYPE_CHECKING:
    from reservations.models.enquiry import Enquiry


class QuotationLineInput(TypedDict, total=False):
    property: Any
    date_from: date_type
    date_to: date_type
    adults: int
    children: int
    notes: str
    is_manual: bool


class QuotationService:
    """Orchestrate quotation creation off the back of an enquiry."""

    @classmethod
    @transaction.atomic
    def create_from_enquiry(
        cls,
        enquiry: Enquiry,
        lines: list[dict[str, Any]],
        *,
        currency: Any,
        terms_version: Any,
        expires_at: Any,
        guest: Any | None = None,
        agent: Any | None = None,
        actor: Any = None,
        allow_changeover_override: bool = False,
    ) -> Quotation:
        """Build Quotation + lines, run PricingEngine per line, place holds."""
        resolved_guest = guest if guest is not None else enquiry.guest
        if resolved_guest is None:
            raise ValueError(
                "Quotation requires a Guest; pass `guest=` or capture one on the enquiry first."
            )

        quotation = Quotation.objects.create(
            enquiry=enquiry,
            guest=resolved_guest,
            agent=agent,
            currency=currency,
            terms_version=terms_version,
            expires_at=expires_at,
        )

        for line_input in lines:
            adults = int(line_input.get("adults", enquiry.adults))
            children = int(line_input.get("children", enquiry.children))
            party = adults + children
            ChangeoverService.validate_arrival(
                line_input["property"],
                line_input["date_from"],
                allow_override=allow_changeover_override,
            )
            quote = PricingEngine.quote(
                property=line_input["property"],
                date_from=line_input["date_from"],
                date_to=line_input["date_to"],
                party=party,
                currency=currency,
            )
            QuotationLine.objects.create(
                quotation=quotation,
                property=line_input["property"],
                date_from=line_input["date_from"],
                date_to=line_input["date_to"],
                adults=adults,
                children=children,
                pricing_snapshot=quote.breakdown,
                total=quote.total.quantize(Decimal("0.01")),
                is_manual=bool(line_input.get("is_manual", False)),
                notes=line_input.get("notes", ""),
            )
            HoldService.place(
                property=line_input["property"],
                date_from=line_input["date_from"],
                date_to=line_input["date_to"],
                expires_at=expires_at,
                reason=BookingHoldReason.QUOTATION_OPEN.value,
                quotation=quotation,
            )

        # Move the enquiry forward.
        if enquiry.status not in (EnquiryStatus.QUOTED.value, EnquiryStatus.CONVERTED.value):
            enquiry.quote_sent(quotation, actor=actor)

        return quotation
