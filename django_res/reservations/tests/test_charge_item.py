"""Model tests for BookingChargeItem — manual charge/credit lines."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.models import Person
from pricing.models import Currency
from properties.models import Property
from reservations.enums import PaymentMethod
from reservations.models import (
    Booking,
    BookingChargeItem,
    Quotation,
    QuotationLine,
    TermsVersion,
)
from reservations.signals import booking_total_changed


@pytest.fixture
def booking(
    db: None,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    person = customer
    quotation = Quotation.objects.create(
        enquiry=person.enquiries_as_customer.create(),
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        person=person,
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
    )


@pytest.mark.django_db
def test_create_and_str(booking: Booking, gbp: Currency) -> None:
    item = BookingChargeItem.objects.create(
        booking=booking,
        label="Late checkout",
        amount=Decimal("150.00"),
        currency=gbp,
        notes="Agreed with guest by phone",
    )
    assert item.pk is not None
    assert item.booking == booking
    assert str(item) == "Late checkout 150.00"
    assert list(booking.charge_items.all()) == [item]


@pytest.mark.django_db
def test_ordering_is_insertion_order(booking: Booking, gbp: Currency) -> None:
    first = BookingChargeItem.objects.create(
        booking=booking, label="A", amount=Decimal("10.00"), currency=gbp
    )
    second = BookingChargeItem.objects.create(
        booking=booking, label="B", amount=Decimal("20.00"), currency=gbp
    )
    assert list(BookingChargeItem.objects.all()) == [first, second]


@pytest.mark.django_db
def test_negative_amount_is_a_credit(booking: Booking, gbp: Currency) -> None:
    item = BookingChargeItem.objects.create(
        booking=booking,
        label="Negotiated discount",
        amount=Decimal("-500.00"),
        currency=gbp,
    )
    assert item.amount == Decimal("-500.00")


@pytest.mark.django_db
def test_zero_amount_violates_check_constraint(booking: Booking, gbp: Currency) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingChargeItem.objects.create(
            booking=booking, label="Nothing", amount=Decimal("0"), currency=gbp
        )


@pytest.mark.django_db
def test_cascade_delete_with_booking(booking: Booking, gbp: Currency) -> None:
    BookingChargeItem.objects.create(
        booking=booking, label="Heli transfer", amount=Decimal("900.00"), currency=gbp
    )
    booking.delete()
    assert BookingChargeItem.objects.count() == 0


# ---------------------------------------------------------------------------
# booking_total_changed signal
# ---------------------------------------------------------------------------


@pytest.fixture
def total_changed_calls(booking: Booking) -> Iterator[list[Booking]]:
    """Capture `booking_total_changed` firings for `booking`."""
    calls: list[Booking] = []

    def _receiver(sender: type, booking: Booking, **_: object) -> None:
        calls.append(booking)

    booking_total_changed.connect(_receiver, dispatch_uid="test.total_changed_capture")
    try:
        yield calls
    finally:
        booking_total_changed.disconnect(dispatch_uid="test.total_changed_capture")


@pytest.mark.django_db
def test_create_fires_booking_total_changed_once(
    booking: Booking, gbp: Currency, total_changed_calls: list[Booking]
) -> None:
    BookingChargeItem.objects.create(
        booking=booking, label="Late checkout", amount=Decimal("150.00"), currency=gbp
    )
    assert total_changed_calls == [booking]


@pytest.mark.django_db
def test_update_fires_booking_total_changed_once(
    booking: Booking, gbp: Currency, total_changed_calls: list[Booking]
) -> None:
    item = BookingChargeItem.objects.create(
        booking=booking, label="Late checkout", amount=Decimal("150.00"), currency=gbp
    )
    total_changed_calls.clear()

    item.amount = Decimal("175.00")
    item.save()
    assert total_changed_calls == [booking]


@pytest.mark.django_db
def test_delete_fires_booking_total_changed_once(
    booking: Booking, gbp: Currency, total_changed_calls: list[Booking]
) -> None:
    item = BookingChargeItem.objects.create(
        booking=booking, label="Late checkout", amount=Decimal("150.00"), currency=gbp
    )
    total_changed_calls.clear()

    item.delete()
    assert total_changed_calls == [booking]
