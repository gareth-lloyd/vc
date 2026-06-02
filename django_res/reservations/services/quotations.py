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
    total: Decimal


class QuotationService:
    """Orchestrate quotation creation off the back of an enquiry."""

    @classmethod
    def price_line(cls, quotation: Quotation, line: QuotationLine) -> QuotationLine:
        """Run the PricingEngine for a line and persist its total + snapshot.

        The single source of truth for line pricing — both the
        enquiry-driven `create_from_enquiry` path and the API
        `QuotationLineViewSet` path funnel through here so a line is priced
        identically however it's created. Manual-override lines must not be
        passed in; the caller decides whether to reprice.
        """
        party = line.adults + line.children
        quote = PricingEngine.quote(
            property=line.property,
            date_from=line.date_from,
            date_to=line.date_to,
            party=party,
            currency=quotation.currency,
        )
        gross = quote.total.quantize(Decimal("0.01"))
        # Annotate the snapshot so the gross (pre-discount engine figure) and
        # the applied discount survive alongside the engine breakdown — the
        # stored `total` is the net the guest pays.
        snapshot = dict(quote.breakdown)
        snapshot["gross"] = f"{gross:.2f}"
        snapshot["discount"] = f"{line.discount:.2f}"
        line.pricing_snapshot = snapshot
        # Net the operator discount; never let a large discount drive the
        # quoted price negative (mirrors Booking's non-negative money intent).
        line.total = max(gross - line.discount, Decimal("0"))
        line.save(update_fields=["pricing_snapshot", "total", "updated_at"])
        return line

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
            # Changeover validation must run before pricing — an invalid
            # arrival aborts the whole atomic block before any line lands.
            ChangeoverService.validate_arrival(
                line_input["property"],
                line_input["date_from"],
                allow_override=allow_changeover_override,
            )
            is_manual = bool(line_input.get("is_manual", False))
            create_kwargs: dict[str, Any] = {
                "quotation": quotation,
                "property": line_input["property"],
                "date_from": line_input["date_from"],
                "date_to": line_input["date_to"],
                "adults": adults,
                "children": children,
                "is_manual": is_manual,
                "notes": line_input.get("notes", ""),
            }
            # A manual line carries the operator-supplied total (or the model
            # default if none given); the engine must not stamp it.
            if is_manual and "total" in line_input:
                create_kwargs["total"] = line_input["total"]
            line = QuotationLine.objects.create(**create_kwargs)
            # Only non-manual lines are priced — mirror the API `_reprice`
            # guard so a manual line keeps its operator total either way.
            if not is_manual:
                cls.price_line(quotation, line)
            HoldService.place(
                property=line_input["property"],
                date_from=line_input["date_from"],
                date_to=line_input["date_to"],
                expires_at=expires_at,
                reason=BookingHoldReason.QUOTATION_OPEN.value,
                quotation=quotation,
            )

        # Move the enquiry forward. The service-layer path is the in-app
        # SMTP flow — manual-mark goes via the dedicated endpoint, never
        # through here — so the audit event is stamped accordingly.
        if enquiry.status not in (EnquiryStatus.QUOTED.value, EnquiryStatus.CONVERTED.value):
            from reservations.services.quotation_transmission import SEND_PATH_SMTP

            enquiry.quote_sent(quotation, send_path=SEND_PATH_SMTP, actor=actor)

        return quotation
