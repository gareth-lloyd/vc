"""Transition guards must check *current DB state*, not in-memory state.

The pattern under test: two Python instances of the same row (an operator
double-click lands as two requests, each deserialising its own instance).
The first transitions; the second — whose in-memory `status` is now stale —
must re-read under lock and refuse, instead of passing the guard and
double-firing the transition (duplicate events, duplicate signals, or a
re-pointed accepted line).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from core.exceptions import InvalidTransition
from pricing.models import Currency
from properties.models import Property
from reservations.enums import (
    BookingStatus,
    EnquiryEventKind,
    EnquiryStatus,
    QuotationStatus,
)
from reservations.models import (
    Booking,
    BookingEvent,
    Enquiry,
    EnquiryEvent,
    Quotation,
    QuotationLine,
    TermsVersion,
)
from reservations.services.bookings import BookingService

if TYPE_CHECKING:
    from accounts.models import Person


@pytest.fixture
def quotation(db: None, customer: Person, terms: TermsVersion) -> Quotation:
    return Quotation.objects.create(
        enquiry=customer.enquiries_as_customer.create(),
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.fixture
def line(quotation: Quotation, property_: Property, gbp: Currency) -> QuotationLine:
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )


@pytest.mark.django_db
def test_booking_transition_refuses_stale_instance(
    quotation: Quotation,
    line: QuotationLine,
    terms: TermsVersion,
) -> None:
    quotation.send()
    booking = BookingService.create_from_quotation_line(line, terms_version=terms)
    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value

    fresh = Booking.objects.get(pk=booking.pk)
    stale = Booking.objects.get(pk=booking.pk)
    fresh.record_deposit()

    with pytest.raises(InvalidTransition):
        stale.record_deposit()

    deposit_events = BookingEvent.objects.filter(
        booking=booking,
        to_status=BookingStatus.DEPOSIT_PAID.value,
    )
    assert deposit_events.count() == 1


@pytest.mark.django_db
def test_quotation_accept_refuses_stale_instance(
    quotation: Quotation,
    line: QuotationLine,
    property_: Property,
    gbp: Currency,
) -> None:
    """A second accept — even via a stale instance, even citing a different
    line — must not re-point the accepted quote."""
    other_line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 7, 10),
        date_to=date(2026, 7, 17),
        adults=2,
        total=Decimal("900.00"),
    )
    quotation.send()
    stale = Quotation.objects.get(pk=quotation.pk)
    quotation.accept(line)

    with pytest.raises(InvalidTransition):
        stale.accept(other_line)

    line.refresh_from_db()
    other_line.refresh_from_db()
    assert line.is_selected is True
    assert other_line.is_selected is False
    quotation.refresh_from_db()
    assert quotation.status == QuotationStatus.ACCEPTED.value


@pytest.mark.django_db
def test_enquiry_transition_refuses_stale_instance(customer: Person) -> None:
    enquiry = Enquiry.objects.create(person=customer, email=customer.primary_email() or "")
    stale = Enquiry.objects.get(pk=enquiry.pk)
    enquiry.contact()

    with pytest.raises(InvalidTransition):
        stale.contact()

    contacted_events = EnquiryEvent.objects.filter(
        enquiry=enquiry,
        kind=EnquiryEventKind.CONTACTED.value,
    )
    assert contacted_events.count() == 1
    enquiry.refresh_from_db()
    assert enquiry.status == EnquiryStatus.PROGRESSING.value
