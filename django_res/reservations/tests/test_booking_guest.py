"""Tests for the BookingGuest through-model + LEAD → Booking.guest sync."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from pricing.models import Currency
from properties.models import Property
from reservations.enums import BookingGuestRole, PaymentMethod
from reservations.models import (
    Booking,
    BookingGuest,
    Guest,
    QuotationLine,
    TermsVersion,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def booking(
    quotation_line: QuotationLine,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    return Booking.objects.create(
        quotation_line=quotation_line,
        guest=guest,
        property=property_,
        date_from=quotation_line.date_from,
        date_to=quotation_line.date_to,
        adults=quotation_line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )


def _make_guest(suffix: str) -> Guest:
    return Guest.objects.create(
        first_name=f"Other{suffix}",
        last_name="Person",
        email=f"other-{suffix}@example.com",
    )


def test_booking_guest_lead_unique_per_booking(booking: Booking) -> None:
    """Only one LEAD row per booking is allowed."""
    other_guest = _make_guest("a")
    BookingGuest.objects.create(
        booking=booking,
        guest=booking.guest,
        role=BookingGuestRole.LEAD.value,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingGuest.objects.create(
            booking=booking,
            guest=other_guest,
            role=BookingGuestRole.LEAD.value,
        )


def test_booking_guest_payer_unique_per_booking(booking: Booking) -> None:
    """At most one PAYER row per booking is allowed."""
    g1 = _make_guest("p1")
    g2 = _make_guest("p2")
    BookingGuest.objects.create(
        booking=booking,
        guest=g1,
        role=BookingGuestRole.PAYER.value,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingGuest.objects.create(
            booking=booking,
            guest=g2,
            role=BookingGuestRole.PAYER.value,
        )


def test_booking_guest_role_unique_per_pair(booking: Booking) -> None:
    """(booking, guest, role) is unique — same trio twice is an error."""
    g = _make_guest("dup")
    BookingGuest.objects.create(
        booking=booking,
        guest=g,
        role=BookingGuestRole.CO_TRAVELLER.value,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingGuest.objects.create(
            booking=booking,
            guest=g,
            role=BookingGuestRole.CO_TRAVELLER.value,
        )


def test_booking_guest_co_traveller_multiple_allowed(booking: Booking) -> None:
    """Multiple CO_TRAVELLER rows on one booking are fine."""
    g1 = _make_guest("c1")
    g2 = _make_guest("c2")
    g3 = _make_guest("c3")
    BookingGuest.objects.create(booking=booking, guest=g1, role=BookingGuestRole.CO_TRAVELLER.value)
    BookingGuest.objects.create(booking=booking, guest=g2, role=BookingGuestRole.CO_TRAVELLER.value)
    BookingGuest.objects.create(booking=booking, guest=g3, role=BookingGuestRole.CO_TRAVELLER.value)
    assert (
        BookingGuest.objects.filter(
            booking=booking,
            role=BookingGuestRole.CO_TRAVELLER.value,
        ).count()
        == 3
    )


def test_booking_guest_lead_syncs_to_booking_guest(
    quotation_line: QuotationLine,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Creating a LEAD row updates Booking.guest to that guest."""
    # Create booking with a placeholder Guest, then attach a different LEAD.
    placeholder = guest
    lead_guest = Guest.objects.create(
        first_name="Lead",
        last_name="Guest",
        email="lead@example.com",
    )
    booking = Booking.objects.create(
        quotation_line=quotation_line,
        guest=placeholder,
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )
    assert booking.guest_id == placeholder.pk

    BookingGuest.objects.create(
        booking=booking,
        guest=lead_guest,
        role=BookingGuestRole.LEAD.value,
    )
    booking.refresh_from_db()
    assert booking.guest_id == lead_guest.pk


def test_booking_guest_lead_change_resyncs(
    quotation_line: QuotationLine,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Changing the LEAD row's guest re-syncs Booking.guest."""
    placeholder = guest
    lead_a = Guest.objects.create(first_name="Alice", last_name="A", email="a@example.com")
    lead_b = Guest.objects.create(first_name="Bob", last_name="B", email="b@example.com")
    booking = Booking.objects.create(
        quotation_line=quotation_line,
        guest=placeholder,
        property=property_,
        date_from=date(2026, 8, 1) + timedelta(days=0),
        date_to=date(2026, 8, 8),
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )
    bg = BookingGuest.objects.create(
        booking=booking,
        guest=lead_a,
        role=BookingGuestRole.LEAD.value,
    )
    booking.refresh_from_db()
    assert booking.guest_id == lead_a.pk

    bg.guest = lead_b
    bg.save(update_fields=["guest", "updated_at"])
    booking.refresh_from_db()
    assert booking.guest_id == lead_b.pk
