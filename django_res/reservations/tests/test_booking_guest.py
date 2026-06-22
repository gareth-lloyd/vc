"""Tests for the BookingGuest through-model + LEAD → Booking.guest sync."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone

from accounts.factories import CustomerPersonFactory
from accounts.models import Person
from pricing.models import Currency
from properties.models import Property
from reservations.enums import BookingGuestRole, PaymentMethod
from reservations.models import (
    Booking,
    BookingGuest,
    QuotationLine,
    TermsVersion,
)
from reservations.signals import LeadGuestProtectedError

pytestmark = pytest.mark.django_db


@pytest.fixture
def booking(
    quotation_line: QuotationLine,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    return Booking.objects.create(
        quotation_line=quotation_line,
        person=customer,
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


def _make_customer(suffix: str) -> Person:
    return cast(
        Person,
        CustomerPersonFactory(
            first_name=f"Other{suffix}",
            last_name="Person",
            primary_email=f"other-{suffix}@example.com",
        ),
    )


def test_booking_guest_lead_unique_per_booking(booking: Booking) -> None:
    """Only one LEAD row per booking is allowed."""
    other_customer = _make_customer("a")
    assert booking.person is not None
    BookingGuest.objects.create(
        booking=booking,
        person=booking.person,
        role=BookingGuestRole.LEAD.value,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingGuest.objects.create(
            booking=booking,
            person=other_customer,
            role=BookingGuestRole.LEAD.value,
        )


def test_booking_guest_payer_unique_per_booking(booking: Booking) -> None:
    """At most one PAYER row per booking is allowed."""
    c1 = _make_customer("p1")
    c2 = _make_customer("p2")
    BookingGuest.objects.create(
        booking=booking,
        person=c1,
        role=BookingGuestRole.PAYER.value,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingGuest.objects.create(
            booking=booking,
            person=c2,
            role=BookingGuestRole.PAYER.value,
        )


def test_booking_guest_role_unique_per_pair(booking: Booking) -> None:
    """(booking, guest, role) is unique — same trio twice is an error."""
    c = _make_customer("dup")
    BookingGuest.objects.create(
        booking=booking,
        person=c,
        role=BookingGuestRole.CO_TRAVELLER.value,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingGuest.objects.create(
            booking=booking,
            person=c,
            role=BookingGuestRole.CO_TRAVELLER.value,
        )


def test_booking_guest_co_traveller_multiple_allowed(booking: Booking) -> None:
    """Multiple CO_TRAVELLER rows on one booking are fine."""
    c1 = _make_customer("c1")
    c2 = _make_customer("c2")
    c3 = _make_customer("c3")
    BookingGuest.objects.create(
        booking=booking,
        person=c1,
        role=BookingGuestRole.CO_TRAVELLER.value,
    )
    BookingGuest.objects.create(
        booking=booking,
        person=c2,
        role=BookingGuestRole.CO_TRAVELLER.value,
    )
    BookingGuest.objects.create(
        booking=booking,
        person=c3,
        role=BookingGuestRole.CO_TRAVELLER.value,
    )
    assert (
        BookingGuest.objects.filter(
            booking=booking,
            role=BookingGuestRole.CO_TRAVELLER.value,
        ).count()
        == 3
    )


def test_booking_guest_lead_syncs_to_booking_guest(
    quotation_line: QuotationLine,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Creating a LEAD row updates Booking.person to that customer (3d-C)."""
    # Create booking with a placeholder customer, then attach a different LEAD.
    placeholder = customer
    lead_customer = cast(
        Person,
        CustomerPersonFactory(
            first_name="Lead",
            last_name="Guest",
            primary_email="lead@example.com",
        ),
    )
    booking = Booking.objects.create(
        quotation_line=quotation_line,
        person=placeholder,
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
    assert booking.person_id == placeholder.pk

    BookingGuest.objects.create(
        booking=booking,
        person=lead_customer,
        role=BookingGuestRole.LEAD.value,
    )
    booking.refresh_from_db()
    assert booking.person_id == lead_customer.pk


def test_booking_guest_lead_change_resyncs(
    quotation_line: QuotationLine,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Changing the LEAD row's person re-syncs Booking.person (3d-C)."""
    placeholder = customer
    lead_a = cast(
        Person,
        CustomerPersonFactory(first_name="Alice", last_name="A", primary_email="a@example.com"),
    )
    lead_b = cast(
        Person,
        CustomerPersonFactory(first_name="Bob", last_name="B", primary_email="b@example.com"),
    )
    booking = Booking.objects.create(
        quotation_line=quotation_line,
        person=placeholder,
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
        person=lead_a,
        role=BookingGuestRole.LEAD.value,
    )
    booking.refresh_from_db()
    assert booking.person_id == lead_a.pk

    bg.person = lead_b
    bg.save(update_fields=["person", "updated_at"])
    booking.refresh_from_db()
    assert booking.person_id == lead_b.pk


def test_booking_guest_lead_delete_raises_while_booking_exists(booking: Booking) -> None:
    """Deleting a LEAD row while its Booking still exists raises ProtectedError.

    The orphan-guard refuses the direct delete because the Booking
    invariant "exactly one LEAD guest" would be violated.
    """
    assert booking.person is not None
    lead_row = BookingGuest.objects.create(
        booking=booking,
        person=booking.person,
        role=BookingGuestRole.LEAD.value,
    )
    with pytest.raises(LeadGuestProtectedError), transaction.atomic():
        lead_row.delete()
    # The custom exception is a ProtectedError subclass, so callers can
    # also catch the broader Django type.
    assert issubclass(LeadGuestProtectedError, ProtectedError)


def test_booking_guest_lead_delete_during_booking_cascade_is_allowed(booking: Booking) -> None:
    """Cascading delete of the parent Booking cleans up the LEAD row, no raise."""
    assert booking.person is not None
    BookingGuest.objects.create(
        booking=booking,
        person=booking.person,
        role=BookingGuestRole.LEAD.value,
    )
    booking_pk = booking.pk
    # No exception expected — Booking.delete() cascades to BookingGuest and
    # the orphan-guard recognises the cascade case by probing for the parent.
    booking.delete()
    assert not BookingGuest.objects.filter(booking_id=booking_pk).exists()
    assert not Booking.objects.filter(pk=booking_pk).exists()


def test_booking_guest_lead_swap_via_role_demotion_succeeds(booking: Booking) -> None:
    """The recommended LEAD-swap pattern: demote, then re-add, in one atomic block."""
    assert booking.person is not None
    old_lead = BookingGuest.objects.create(
        booking=booking,
        person=booking.person,
        role=BookingGuestRole.LEAD.value,
    )
    new_lead_customer = _make_customer("new-lead")

    with transaction.atomic():
        # Demote the old LEAD row to CO_TRAVELLER so the partial unique
        # constraint releases.
        BookingGuest.objects.filter(pk=old_lead.pk).update(
            role=BookingGuestRole.CO_TRAVELLER.value,
        )
        # Create the new LEAD row.
        BookingGuest.objects.create(
            booking=booking,
            person=new_lead_customer,
            role=BookingGuestRole.LEAD.value,
        )

    booking.refresh_from_db()
    assert booking.person_id == new_lead_customer.pk
    assert (
        BookingGuest.objects.filter(
            booking=booking,
            role=BookingGuestRole.LEAD.value,
        ).count()
        == 1
    )
    assert BookingGuest.objects.filter(
        pk=old_lead.pk,
        role=BookingGuestRole.CO_TRAVELLER.value,
    ).exists()
