"""GAP-045 Unit 3d-A — `person` is the authoritative customer FK at the DB.

After migration 0034: `person` is NOT NULL on Quotation/Booking/BookingGuest/
GuestPreference, `guest` is nullable on the same four, and the two formerly
guest-keyed uniqueness rules are repointed onto `person`
(`bookingguest_unique_booking_person_role`, `unique_person_preference`).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from pricing.models import Currency
from properties.models import Property
from reservations.enums import BookingGuestRole
from reservations.factories import make_occupying_booking
from reservations.models import (
    Booking,
    BookingGuest,
    Guest,
    GuestPreference,
    GuestPreferenceType,
    Quotation,
    TermsVersion,
)
from reservations.services.person_sync import person_for_guest

pytestmark = pytest.mark.django_db


def _pref_type() -> GuestPreferenceType:
    return GuestPreferenceType.objects.create(name="Late checkout")


# --- person is now required ------------------------------------------------


def test_quotation_requires_person(guest: Guest, terms: TermsVersion) -> None:
    person = person_for_guest(guest)
    with pytest.raises(IntegrityError), transaction.atomic():
        Quotation.objects.create(  # type: ignore[misc]
            enquiry=guest.enquiries.create(person=person),
            guest=guest,
            person=None,
            expires_at=timezone.now() + timedelta(days=7),
            terms_version=terms,
        )


def test_guest_preference_requires_person(guest: Guest) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        GuestPreference.objects.create(  # type: ignore[misc]
            guest=guest, person=None, preference_type=_pref_type()
        )


def test_booking_requires_person(
    guest: Guest, property_: Property, gbp: Currency, terms: TermsVersion
) -> None:
    booking = make_occupying_booking(
        property=property_,
        person=person_for_guest(guest),
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    # A bulk .update() bypasses Python but must still hit the DB NOT-NULL.
    with pytest.raises(IntegrityError), transaction.atomic():
        Booking.objects.filter(pk=booking.pk).update(person=None)


def test_booking_guest_requires_person(
    guest: Guest, property_: Property, gbp: Currency, terms: TermsVersion
) -> None:
    booking = make_occupying_booking(
        property=property_,
        person=person_for_guest(guest),
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingGuest.objects.create(  # type: ignore[misc]
            booking=booking,
            guest=guest,
            person=None,
            role=BookingGuestRole.CO_TRAVELLER.value,
        )


# --- guest is now optional -------------------------------------------------


def test_guest_preference_allows_null_guest(guest: Guest) -> None:
    """A person-only preference (no legacy guest leg) saves cleanly."""
    person = person_for_guest(guest)
    pref = GuestPreference.objects.create(guest=None, person=person, preference_type=_pref_type())
    assert pref.guest_id is None
    assert pref.person_id == person.pk


# --- uniqueness repointed onto person --------------------------------------


def test_unique_person_preference_repointed(guest: Guest, terms: TermsVersion) -> None:
    person = person_for_guest(guest)
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(person=person),
        guest=guest,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    pref_type = _pref_type()
    GuestPreference.objects.create(person=person, preference_type=pref_type, quotation=quotation)
    with pytest.raises(IntegrityError), transaction.atomic():
        GuestPreference.objects.create(
            person=person, preference_type=pref_type, quotation=quotation
        )


def test_bookingguest_unique_booking_person_role_repointed(
    guest: Guest, property_: Property, gbp: Currency, terms: TermsVersion
) -> None:
    booking = make_occupying_booking(
        property=property_,
        person=person_for_guest(guest),
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    person = person_for_guest(guest)
    BookingGuest.objects.create(
        booking=booking, guest=guest, person=person, role=BookingGuestRole.CO_TRAVELLER.value
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        BookingGuest.objects.create(
            booking=booking,
            guest=guest,
            person=person,
            role=BookingGuestRole.CO_TRAVELLER.value,
        )
