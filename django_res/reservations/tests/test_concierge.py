"""Tests for BookingConciergeItem → Booking.adjustment signal recompute."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from reservations.enums import ConciergeStatus, ConciergeTier, ConciergeUnit, PaymentMethod
from reservations.models import (
    Booking,
    BookingConciergeItem,
    Quotation,
    QuotationLine,
)

if TYPE_CHECKING:
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import Guest, TermsVersion


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
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )


@pytest.mark.django_db
def test_concierge_item_save_updates_adjustment(booking: Booking, gbp: Currency) -> None:
    BookingConciergeItem.objects.create(
        booking=booking,
        tier=ConciergeTier.SIGNATURE.value,
        name="Private chef",
        quantity=2,
        unit=ConciergeUnit.EVENT.value,
        unit_price=Decimal("300.00"),
        currency=gbp,
    )
    booking.refresh_from_db()
    assert booking.adjustment == Decimal("600.00")


@pytest.mark.django_db
def test_concierge_item_cancelled_excluded(booking: Booking, gbp: Currency) -> None:
    BookingConciergeItem.objects.create(
        booking=booking,
        tier=ConciergeTier.QUINTESSENTIAL.value,
        name="Housekeeping",
        quantity=7,
        unit=ConciergeUnit.DAY.value,
        unit_price=Decimal("80.00"),
        currency=gbp,
        status=ConciergeStatus.CONFIRMED.value,
    )
    BookingConciergeItem.objects.create(
        booking=booking,
        tier=ConciergeTier.QUINTESSENTIAL.value,
        name="Pet care",
        quantity=3,
        unit=ConciergeUnit.DAY.value,
        unit_price=Decimal("50.00"),
        currency=gbp,
        status=ConciergeStatus.CANCELLED.value,
    )
    booking.refresh_from_db()
    assert booking.adjustment == Decimal("560.00")  # 7*80


@pytest.mark.django_db
def test_concierge_item_delete_recomputes(booking: Booking, gbp: Currency) -> None:
    item = BookingConciergeItem.objects.create(
        booking=booking,
        tier=ConciergeTier.SIGNATURE.value,
        name="Driver",
        quantity=1,
        unit=ConciergeUnit.STAY.value,
        unit_price=Decimal("500.00"),
        currency=gbp,
    )
    booking.refresh_from_db()
    assert booking.adjustment == Decimal("500.00")
    item.delete()
    booking.refresh_from_db()
    assert booking.adjustment == Decimal("0.00")
