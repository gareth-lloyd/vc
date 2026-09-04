"""Unit tests for `seeding._booking_helpers.advance_status`.

BUG-026: `PaymentScheduler.create_for_booking` can now advance a booking
straight to DEPOSIT_PAID when no deposit is wanted, before `advance_status`
gets a turn. Its unconditional `booking.record_deposit()` call would then
race an already-DEPOSIT_PAID booking and crash `seed_dev` with
`InvalidTransition`. This pins the defensive guard added alongside that
change: `advance_status` must skip a redundant `record_deposit()` and still
complete the rest of the walk.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.utils import timezone

from accounts.models import Person
from pricing.factories import CurrencyFactory
from pricing.models import Currency
from properties.factories import PropertyFactory
from properties.models import Property
from reservations.enums import BookingStatus, PaymentMethod
from reservations.factories import TermsVersionFactory, make_occupying_booking
from reservations.models import Booking, TermsVersion
from seeding._booking_helpers import advance_status
from seeding.context import ProfileKnobs, SeedContext

pytestmark = pytest.mark.django_db


def _ctx() -> SeedContext:
    return SeedContext(
        rng=random.Random(1),
        knobs=ProfileKnobs(name="test"),
        n_properties=1,
        n_bookings=1,
        n_users=1,
    )


def _booking() -> Booking:
    from accounts.factories import CustomerPersonFactory

    currency = cast(Currency, CurrencyFactory())
    terms = cast(TermsVersion, TermsVersionFactory())
    person = cast(Person, CustomerPersonFactory())
    property_ = cast(Property, PropertyFactory())
    date_from = date.today() + timedelta(days=30)
    booking = make_occupying_booking(
        property=property_,
        person=person,
        currency=currency,
        terms=terms,
        date_from=date_from,
        date_to=date_from + timedelta(days=7),
    )
    booking.payment_method = PaymentMethod.CARD.value
    booking.save(update_fields=["payment_method"])
    return booking


def _mark_pending_deposit_paid(booking: Booking) -> None:
    """Stand in for a real settle so `mark_payment_paid` has a row to find."""
    from payments.enums import PaymentPurpose, PaymentStatus
    from payments.models.payment import Payment

    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("100.00"),
        currency=booking.currency,
        due_at=timezone.now(),
    )


def test_advance_status_skips_redundant_record_deposit_when_already_paid() -> None:
    booking = _booking()
    booking.skip_deposit()  # simulate the scheduler already advancing it
    ctx = _ctx()

    # track = i % 6 == 2 walks through record_deposit -> arm_balance -> record_balance.
    advance_status(booking, 2, ctx)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.BALANCE_PAID.value


def test_advance_status_normal_path_unaffected() -> None:
    booking = _booking()
    _mark_pending_deposit_paid(booking)
    ctx = _ctx()

    advance_status(booking, 2, ctx)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.BALANCE_PAID.value
