"""Tests for QuotationService.create_from_enquiry."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from core.exceptions import ChangeoverViolation
from properties.enums import PrefilledChangeOverDay
from properties.models.settings import PropertySettings
from reservations.enums import BookingHoldReason, EnquiryStatus
from reservations.models import BookingHold, Enquiry, Quotation
from reservations.services.quotations import QuotationService

if TYPE_CHECKING:
    from pricing.models import Currency, RateRule
    from properties.models import Property
    from reservations.models import Guest, TermsVersion


@pytest.mark.django_db
def test_create_from_enquiry_happy_path(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,  # ensures PricingEngine has something to quote on
) -> None:
    enquiry = Enquiry.objects.create(guest=guest, email=guest.email)
    expires = timezone.now() + timedelta(days=7)

    quotation = QuotationService.create_from_enquiry(
        enquiry,
        [
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
                "adults": 2,
                "children": 0,
            },
        ],
        currency=gbp,
        terms_version=terms,
        expires_at=expires,
    )

    assert isinstance(quotation, Quotation)
    assert quotation.lines.count() == 1
    line = quotation.lines.first()
    assert line is not None
    assert line.pricing_snapshot["rate_subtotal"] == "1400.00"

    # Hold placed for the line's dates and property.
    holds = BookingHold.objects.filter(quotation=quotation)
    assert holds.count() == 1
    hold = holds.first()
    assert hold is not None
    assert hold.reason == BookingHoldReason.QUOTATION_OPEN.value

    # Enquiry advanced to QUOTED.
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.QUOTED.value


@pytest.mark.django_db
def test_create_from_enquiry_does_not_reprice_manual_line(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """A manual enquiry line keeps its supplied total — the engine must not
    clobber it, mirroring the API `_reprice` guard."""
    from decimal import Decimal

    enquiry = Enquiry.objects.create(guest=guest, email=guest.email)

    quotation = QuotationService.create_from_enquiry(
        enquiry,
        [
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
                "adults": 2,
                "children": 0,
                "is_manual": True,
                "total": Decimal("750.00"),
            },
        ],
        currency=gbp,
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )

    line = quotation.lines.get()
    assert line.is_manual is True
    # Engine price would be 7 nights @ £200 = £1400; the manual total survives.
    assert line.total == Decimal("750.00")
    assert line.pricing_snapshot == {}


@pytest.mark.django_db
def test_create_from_enquiry_requires_guest(
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    enquiry = Enquiry.objects.create(email="anonymous@example.com")
    with pytest.raises(ValueError):
        QuotationService.create_from_enquiry(
            enquiry,
            [
                {
                    "property": property_,
                    "date_from": date(2026, 6, 10),
                    "date_to": date(2026, 6, 17),
                    "adults": 2,
                },
            ],
            currency=gbp,
            terms_version=terms,
            expires_at=timezone.now() + timedelta(days=7),
        )


@pytest.mark.django_db
def test_create_from_enquiry_records_send_path_smtp(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """Bug #6: `QuotationService.create_from_enquiry` was calling
    `enquiry.quote_sent(quotation, actor=actor)` with no `meta`, so the
    resulting EnquiryEvent had no `send_path` key — breaking the invariant
    the manual-mark endpoint relies on. The service path is SMTP by
    contract (Quotation built off the back of an enquiry, dispatched
    through the in-app flow), so the event must carry send_path='smtp'.
    """
    from reservations.enums import EnquiryEventKind
    from reservations.models import EnquiryEvent

    enquiry = Enquiry.objects.create(guest=guest, email=guest.email)

    QuotationService.create_from_enquiry(
        enquiry,
        [
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
                "adults": 2,
            },
        ],
        currency=gbp,
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )

    event = EnquiryEvent.objects.get(enquiry=enquiry, kind=EnquiryEventKind.QUOTE_SENT.value)
    assert event.meta.get("send_path") == "smtp"


@pytest.mark.django_db
def test_quote_sent_requires_send_path(guest: Guest, gbp: Currency, terms: TermsVersion) -> None:
    """`Enquiry.quote_sent` must require `send_path` — surfacing the audit
    contract in the signature so future callers can't omit it silently."""
    enquiry = Enquiry.objects.create(guest=guest, email=guest.email)
    quotation = Quotation.objects.create(
        enquiry=enquiry,
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )

    with pytest.raises(TypeError):
        enquiry.quote_sent(quotation)  # type: ignore[call-arg]


@pytest.mark.django_db
def test_create_from_enquiry_enforces_changeover(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    PropertySettings.objects.create(
        property=property_,
        changeover_day=PrefilledChangeOverDay.SAT.value,
    )
    enquiry = Enquiry.objects.create(guest=guest, email=guest.email)
    # 2026-06-10 is a Wednesday — not the Saturday changeover day.
    line = {
        "property": property_,
        "date_from": date(2026, 6, 10),
        "date_to": date(2026, 6, 17),
        "adults": 2,
    }

    with pytest.raises(ChangeoverViolation):
        QuotationService.create_from_enquiry(
            enquiry,
            [line],
            currency=gbp,
            terms_version=terms,
            expires_at=timezone.now() + timedelta(days=7),
        )

    quotation = QuotationService.create_from_enquiry(
        enquiry,
        [line],
        currency=gbp,
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
        allow_changeover_override=True,
    )
    assert quotation.lines.count() == 1
    assert BookingHold.objects.filter(quotation=quotation).count() == 1
