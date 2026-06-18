"""GAP-045 Unit 3b — tests for the Person-from-Guest backfill migration
(``reservations/0033_backfill_person_from_guest``).

There is no migration-test framework in this repo (0022/0026 ship none, and
``django-test-migrations`` is not a dependency). Simplest viable approach:
call the module-level ``_forwards`` / ``_reverse`` callables directly with the
live app registry (``django.apps.apps``), since the historical and concrete
models share a schema in a single-migration-state test DB.
"""

from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import TYPE_CHECKING, cast

import pytest
from django.apps import apps

from accounts.models import Person, PersonEmail, PersonPhone
from reservations.enums import BookingGuestRole, ContactMethod, GuestStatus
from reservations.factories import EnquiryFactory, GuestFactory, make_occupying_booking
from reservations.models import Enquiry, Guest, GuestPreference, GuestPreferenceType

if TYPE_CHECKING:
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import TermsVersion

_migration = import_module("reservations.migrations.0033_backfill_person_from_guest")

pytestmark = pytest.mark.django_db


def _forward() -> None:
    _migration._forwards(apps, None)


def _reverse() -> None:
    _migration._reverse(apps, None)


def _person_for(guest: Guest) -> Person:
    return Person.objects.get(legacy_id=f"guest-{guest.pk}")


def test_creates_one_person_per_guest_with_mapped_fields() -> None:
    guest = cast(
        Guest,
        GuestFactory(
            title="Dr",
            first_name="Ada",
            last_name="Lovelace",
            address_line_1="1 Analytical Way",
            town="London",
            post_code="EC1",
            contact_method=ContactMethod.EMAIL,
            marketing_consent=True,
            notes="VIP",
            status=GuestStatus.ACTIVE,
        ),
    )

    _forward()

    assert Person.objects.filter(legacy_id__startswith="guest-").count() == 1
    person = _person_for(guest)
    assert person.title == "Dr"
    assert person.first_name == "Ada"
    assert person.last_name == "Lovelace"
    assert person.address_line_1 == "1 Analytical Way"
    assert person.town == "London"
    assert person.post_code == "EC1"
    assert person.country_id == guest.country_id
    assert person.marketing_consent is True
    assert person.notes == "VIP"
    assert person.status == "active"
    assert person.preferred_method == "email"
    # user OneToOne is deferred to Unit 3d.
    assert person.user_id is None

    email = PersonEmail.objects.get(contact=person)
    assert email.email == guest.email
    assert email.label == "primary"
    assert email.is_primary is True

    phone = PersonPhone.objects.get(contact=person)
    # Copied verbatim — whatever Guest.save's to_e164 left behind.
    assert phone.number == guest.phone
    assert phone.label == "mobile"
    assert phone.is_primary is True


@pytest.mark.parametrize(
    ("guest_status", "expected"),
    [
        (GuestStatus.ACTIVE, "active"),
        (GuestStatus.ARCHIVED, "inactive"),
        (GuestStatus.ANONYMIZED, "anonymized"),
    ],
)
def test_status_mapping(guest_status: GuestStatus, expected: str) -> None:
    guest = cast(Guest, GuestFactory(status=guest_status))

    _forward()

    assert _person_for(guest).status == expected


def test_preferred_method_defaults_email_when_unset_and_preserved_when_set() -> None:
    no_pref = cast(Guest, GuestFactory(contact_method=None))
    phone_pref = cast(Guest, GuestFactory(contact_method=ContactMethod.PHONE))

    _forward()

    assert _person_for(no_pref).preferred_method == "email"
    assert _person_for(phone_pref).preferred_method == "phone"


def test_skips_channel_children_when_guest_has_none() -> None:
    # Channel-less is only legal off the ACTIVE path (the contactable CHECK).
    guest = cast(
        Guest,
        GuestFactory(status=GuestStatus.ANONYMIZED, email=None, phone=""),
    )

    _forward()

    person = _person_for(guest)
    assert not PersonEmail.objects.filter(contact=person).exists()
    assert not PersonPhone.objects.filter(contact=person).exists()


def test_app_born_guest_with_null_legacy_id_still_gets_a_person() -> None:
    guest = cast(Guest, GuestFactory(legacy_id=None))
    assert guest.legacy_id is None

    _forward()

    assert _person_for(guest).legacy_id == f"guest-{guest.pk}"


def test_links_parallel_person_fks() -> None:
    enquiry = cast(Enquiry, EnquiryFactory())
    guest = cast(Guest, enquiry.guest)
    ptype = GuestPreferenceType.objects.create(name="Sea View")
    pref = GuestPreference.objects.create(guest=guest, preference_type=ptype)

    _forward()

    person = _person_for(guest)
    enquiry.refresh_from_db()
    pref.refresh_from_db()
    assert enquiry.person_id == person.pk
    assert pref.person_id == person.pk


def test_links_booking_quotation_and_bookingguest_to_one_person(
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    # make_occupying_booking builds Quotation → line → Booking → LEAD
    # BookingGuest, all bound to one guest — exercising the three FK links the
    # Enquiry/GuestPreference test can't reach (Booking/Quotation are
    # service-built). Booking.person resolves via the denormalised Booking.guest
    # = LEAD BookingGuest.guest, so all three must land on the SAME Person.
    guest = cast(Guest, GuestFactory())
    booking = make_occupying_booking(
        property=property_,
        guest=guest,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 7, 4),
        date_to=date(2026, 7, 11),
    )

    _forward()

    person = _person_for(guest)
    booking.refresh_from_db()
    lead = booking.booking_guests.get(role=BookingGuestRole.LEAD)
    quotation = booking.quotation_line.quotation
    quotation.refresh_from_db()
    assert booking.person_id == person.pk
    assert lead.person_id == person.pk
    assert quotation.person_id == person.pk


def test_rerun_is_a_noop() -> None:
    enquiry = cast(Enquiry, EnquiryFactory())
    guest = cast(Guest, enquiry.guest)

    _forward()
    _forward()

    assert Person.objects.filter(legacy_id=f"guest-{guest.pk}").count() == 1
    person = _person_for(guest)
    assert PersonEmail.objects.filter(contact=person).count() == 1
    assert PersonPhone.objects.filter(contact=person).count() == 1
    enquiry.refresh_from_db()
    assert enquiry.person_id == person.pk


def test_reverse_unlinks_and_deletes_guest_persons() -> None:
    enquiry = cast(Enquiry, EnquiryFactory())
    guest = cast(Guest, enquiry.guest)

    _forward()
    person = _person_for(guest)
    _reverse()

    assert not Person.objects.filter(legacy_id__startswith="guest-").exists()
    assert not PersonEmail.objects.filter(contact_id=person.pk).exists()
    assert not PersonPhone.objects.filter(contact_id=person.pk).exists()
    enquiry.refresh_from_db()
    assert enquiry.person_id is None
