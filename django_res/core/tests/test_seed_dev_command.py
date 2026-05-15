"""End-to-end coherence test for the seed_dev command."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from payments.models.payment import Payment
from properties.models import Property
from reservations.models.booking import Booking, BookingEvent
from reservations.models.quotation import Quotation

pytestmark = pytest.mark.django_db


def _run(properties: int = 2, bookings: int = 3) -> None:
    call_command(
        "seed_dev",
        "--properties",
        str(properties),
        "--bookings",
        str(bookings),
        "--seed",
        "1",
        stdout=StringIO(),
    )


def test_seed_dev_builds_a_coherent_graph() -> None:
    # 3 bookings span tracks 0/1/2 -> AWAITING_DEPOSIT/DEPOSIT_PAID/BALANCE_PAID,
    # enough to assert the status spread without the full preset's cost.
    _run()

    prop = Property.objects.filter(rate_plans__isnull=False).first()
    assert prop is not None
    # The 1:1 children the booking/pricing services walk.
    assert prop.location is not None
    assert prop.capacity is not None
    assert prop.finance is not None
    assert prop.hero_image() is not None

    booking = Booking.objects.select_related("quotation_line").first()
    assert booking is not None
    assert BookingEvent.objects.filter(booking=booking).exists()
    assert Quotation.objects.exists()
    assert Payment.objects.filter(booking=booking).exists()

    # Status spread: not every booking sits in one bucket.
    statuses = set(Booking.objects.values_list("status", flat=True))
    assert len(statuses) > 1


def test_seed_dev_is_additive_on_rerun() -> None:
    _run(properties=1, bookings=1)
    first = Booking.objects.count()
    _run(properties=1, bookings=1)
    assert Booking.objects.count() > first  # appended, no unique-constraint error
