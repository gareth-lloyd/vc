"""QuotationService — build a Quotation+lines from an Enquiry, place holds."""

from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING, Any, TypedDict

from django.db import transaction

from pricing.services import PricingEngine
from reservations.enums import BookingHoldReason, EnquirySource, EnquiryStatus
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
        # The engine may have nudged the arrival forward to the property's
        # changeover day (GAP-007). Persist the dates it actually priced so the
        # line, its hold, and any downstream booking stay coherent with the
        # snapshot; `changeover_shifted_from` in the snapshot carries the
        # original arrival for the "we moved your dates" note.
        line.date_from = quote.date_from
        line.date_to = quote.date_to
        line.save(update_fields=["pricing_snapshot", "total", "date_from", "date_to", "updated_at"])
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
            # Hold the line's *persisted* dates: pricing may have nudged a
            # non-conforming arrival forward to the changeover day, so we must
            # hold what we priced, not the raw requested dates.
            HoldService.place(
                property=line.property,
                date_from=line.date_from,
                date_to=line.date_to,
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

    @classmethod
    def minimal_enquiry_for(cls, guest: Any, *, agent: Any | None = None) -> Enquiry:
        """Auto-create a minimal Enquiry from a Guest snapshot.

        The single mechanism behind "every quote has an enquiry" for
        agent-direct quotes that arrive with no enquiry (legacy
        `sp_quotationMaster @EnquireId=0` parity). Tagged via the existing
        `site_source=AGENT_PORTAL` so conversion reporting (per-Enquiry) can
        segment these. No sentinel, no nullable bridge, no forced capture step.
        """
        from reservations.models.enquiry import Enquiry

        return Enquiry.objects.create(
            guest=guest,
            first_name=guest.first_name,
            last_name=guest.last_name,
            email=guest.email or "",
            phone=guest.phone,
            contact_method=guest.contact_method,
            agent=agent,
            site_source=EnquirySource.AGENT_PORTAL.value,
        )

    @classmethod
    @transaction.atomic
    def create_direct(
        cls,
        *,
        guest: Any,
        lines: list[dict[str, Any]],
        currency: Any,
        terms_version: Any,
        expires_at: Any,
        agent: Any | None = None,
        actor: Any = None,
    ) -> Quotation:
        """Agent-direct quote with no enquiry — auto-create one, then delegate."""
        enquiry = cls.minimal_enquiry_for(guest, agent=agent)
        return cls.create_from_enquiry(
            enquiry,
            lines,
            currency=currency,
            terms_version=terms_version,
            expires_at=expires_at,
            guest=guest,
            agent=agent,
            actor=actor,
        )
