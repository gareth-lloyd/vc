"""Unit tests for ConciergeCoverageService.set_status."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from pricing.models import Currency
from properties.models import Property
from reservations.enums import BookingStatus, PaymentMethod, ServiceStatus
from reservations.models import (
    Booking,
    BookingServiceCoverage,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)
from reservations.services.service_coverage import ConciergeCoverageService

pytestmark = pytest.mark.django_db


@pytest.fixture
def booking(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    quotation = Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date.today() + timedelta(days=10),
        date_to=date.today() + timedelta(days=17),
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property_,
        date_from=line.date_from,
        date_to=line.date_to,
        adults=line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )


def test_set_status_creates_coverage_row(booking: Booking) -> None:
    coverage = ConciergeCoverageService.set_status(
        booking=booking, service="chef", status=ServiceStatus.WORKING_ON_IT.value
    )
    assert coverage.pk is not None
    assert coverage.booking_id == booking.pk
    assert coverage.service == "chef"
    assert coverage.status == ServiceStatus.WORKING_ON_IT.value


def test_set_status_is_idempotent_upsert(booking: Booking) -> None:
    """A second call for the same (booking, service) updates, never duplicates."""
    first = ConciergeCoverageService.set_status(
        booking=booking, service="chef", status=ServiceStatus.WORKING_ON_IT.value
    )
    second = ConciergeCoverageService.set_status(
        booking=booking, service="chef", status=ServiceStatus.DONE.value
    )
    assert second.pk == first.pk
    assert second.status == ServiceStatus.DONE.value
    assert BookingServiceCoverage.objects.filter(booking=booking, service="chef").count() == 1
