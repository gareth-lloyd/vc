"""GAP-045 — every customer write path fills `person`; 3d-C drops the guest leg.

The reservation models carried a parallel `person` FK alongside `guest` through
the expand/contract cutover. Unit 3c-1b made every write set `person`; Unit 3d-C
made `person` the SOLE persisted customer FK on the production request/service
paths (services / EnquiryWriteSerializer / denorm signal / :duplicate action) —
those now write `guest=None`. Dev/test tooling (factories, make_occupying_booking,
seeding) still writes the harmless nullable guest leg until 3d-E removes the
field. These tests drive each path and assert `person` landed, and that the
production paths no longer persist `guest`.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.models import Currency
from properties.models import Property
from reservations.enums import BookingGuestRole
from reservations.factories import make_occupying_booking
from reservations.models import (
    BookingGuest,
    Enquiry,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)
from reservations.models.preferences import GuestPreference, GuestPreferenceType
from reservations.services.bookings import BookingService
from reservations.services.person_sync import person_for_guest
from reservations.services.quotations import QuotationService


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="res-staff-personfk@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def other_guest(db: None) -> Guest:
    return Guest.objects.create(
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
    )


# ---------------------------------------------------------------------------
# Enquiry — the DRF write path (most important: no service layer)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_enquiry_create_via_api_sets_person(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {
            "guest": guest.pk,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@personfk.example.com",
            "adults": 2,
        },
        format="json",
    )

    assert response.status_code == 201
    enquiry = Enquiry.objects.get(pk=response.data["id"])
    assert enquiry.person is not None
    assert enquiry.person == person_for_guest(guest)
    # 3d-C: `guest` is a writable INPUT (the API still accepts it) but is no
    # longer persisted — only `person` is stored.
    assert enquiry.guest_id is None


@pytest.mark.django_db
def test_enquiry_patch_changing_guest_repoints_person(
    api_client: APIClient, staff: User, guest: Guest, other_guest: Guest
) -> None:
    enquiry = Enquiry.objects.create(
        guest=guest,
        person=person_for_guest(guest),
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        adults=2,
    )
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/enquiries/{enquiry.pk}",
        {"guest": other_guest.pk},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    # 3d-C: the PATCH repoints `person` from the guest input but does NOT persist
    # the guest leg — it stays frozen at its setup value (guest is going away).
    assert enquiry.person == person_for_guest(other_guest)
    assert enquiry.guest == guest


@pytest.mark.django_db
def test_enquiry_patch_not_touching_guest_leaves_person(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    enquiry = Enquiry.objects.create(
        guest=guest,
        person=person_for_guest(guest),
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        adults=2,
    )
    api_client.force_login(staff)

    response = api_client.patch(
        f"/api/v1/enquiries/{enquiry.pk}",
        {"adults": 4},
        format="json",
    )

    assert response.status_code == 200
    enquiry.refresh_from_db()
    assert enquiry.adults == 4
    assert enquiry.person == person_for_guest(guest)


# ---------------------------------------------------------------------------
# Quotation — QuotationService
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_quotation_create_from_enquiry_sets_person(
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
    rate_rule: object,
) -> None:
    enquiry = Enquiry.objects.create(
        guest=guest,
        person=person_for_guest(guest),
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        adults=2,
    )
    quotation = QuotationService.create_from_enquiry(
        enquiry,
        [
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
            }
        ],
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )

    assert quotation.person is not None
    assert quotation.person == person_for_guest(guest)
    assert quotation.guest_id is None  # 3d-C: person is the sole persisted FK


@pytest.mark.django_db
def test_quotation_create_direct_sets_person_on_quotation_and_enquiry(
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
    rate_rule: object,
) -> None:
    quotation = QuotationService.create_direct(
        guest=guest,
        lines=[
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
            }
        ],
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )

    expected = person_for_guest(guest)
    assert quotation.person == expected
    # The auto-minted enquiry must also carry the mirror.
    assert quotation.enquiry.person == expected
    # 3d-C: neither the quotation nor its minted enquiry persists the guest leg.
    assert quotation.guest_id is None
    assert quotation.enquiry.guest_id is None


# ---------------------------------------------------------------------------
# Booking + LEAD BookingGuest — BookingService
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_booking_from_quotation_line_sets_person_on_booking_and_lead(
    quotation_line: QuotationLine,
    terms: TermsVersion,
) -> None:
    guest = quotation_line.quotation.guest
    assert guest is not None
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)

    expected = person_for_guest(guest)
    assert booking.person == expected
    lead = BookingGuest.objects.get(booking=booking, role=BookingGuestRole.LEAD.value)
    assert lead.person == expected
    # 3d-C: the booking + LEAD are born person-only — no legacy guest leg.
    assert booking.guest_id is None
    assert lead.guest_id is None


# ---------------------------------------------------------------------------
# make_occupying_booking factory
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_make_occupying_booking_sets_person_everywhere(
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    booking = make_occupying_booking(
        property=property_,
        guest=guest,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
    )

    expected = person_for_guest(guest)
    assert booking.person == expected
    lead = BookingGuest.objects.get(booking=booking, role=BookingGuestRole.LEAD.value)
    assert lead.person == expected
    assert booking.quotation_line.quotation.person == expected


# ---------------------------------------------------------------------------
# Denorm signal — LEAD BookingGuest mirrors person onto Booking
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_lead_booking_guest_save_mirrors_person_to_booking(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    other_guest: Guest,
) -> None:
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    lead = BookingGuest.objects.get(booking=booking, role=BookingGuestRole.LEAD.value)

    # Re-point the LEAD row at a different person and save — 3d-C: the post_save
    # signal mirrors ONLY `person` onto the denormalised Booking (the guest leg is
    # no longer persisted by any writer).
    new_person = person_for_guest(other_guest)
    lead.person = new_person
    lead.save(update_fields=["person", "updated_at"])

    booking.refresh_from_db()
    assert booking.person == new_person
    assert booking.guest_id is None


# ---------------------------------------------------------------------------
# GuestPreference write path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guest_preference_loader_transform_sets_person(guest: Guest) -> None:
    """The legacy loader's transform must carry `person` into the upsert."""
    from data_migration.loaders.preferences import GuestPreferenceLoader

    # Loader resolves the type by legacy_id, so the row must exist (unused var).
    GuestPreferenceType.objects.create(name="Late checkout", legacy_id="pt-1")
    guest.legacy_id = "g-1"
    guest.save(update_fields=["legacy_id", "updated_at"])

    loader = GuestPreferenceLoader()
    kwargs = loader.transform(
        {
            "Id": "1",
            "ClientDetailsId": "g-1",
            "ClientPrefMasterId": "pt-1",
            "QuotationMasterId": None,
        }
    )

    assert kwargs is not None
    assert kwargs["person"] == person_for_guest(guest)

    pref = GuestPreference.objects.create(**kwargs)
    assert pref.person == person_for_guest(guest)


# ---------------------------------------------------------------------------
# Quotation :duplicate — live DRF action (no service layer)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_quotation_duplicate_action_sets_person_on_clone(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
    rate_rule: object,
) -> None:
    source = QuotationService.create_direct(
        guest=guest,
        lines=[
            {
                "property": property_,
                "date_from": date(2026, 6, 10),
                "date_to": date(2026, 6, 17),
            }
        ],
        terms_version=terms,
        expires_at=timezone.now() + timedelta(days=7),
    )
    api_client.force_login(staff)

    response = api_client.post(f"/api/v1/quotations/{source.pk}/duplicate")

    assert response.status_code == 201
    clone = Quotation.objects.get(pk=response.data["id"])
    assert clone.pk != source.pk
    assert clone.person == person_for_guest(guest)
    assert clone.guest_id is None  # 3d-C: clone carries only the person FK


# ---------------------------------------------------------------------------
# Legacy loaders — ensure_enquiry + QuotationLoader.transform
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ensure_enquiry_sets_person(guest: Guest) -> None:
    """Both legacy quotation paths back-create enquiries through ensure_enquiry."""
    from data_migration.loaders._util import ensure_enquiry

    enquiry = ensure_enquiry(guest, legacy_id="ensure-1")

    assert enquiry.person == person_for_guest(guest)


@pytest.mark.django_db
def test_quotation_loader_transform_sets_person(guest: Guest) -> None:
    from data_migration.loaders.finance import QuotationLoader

    guest.legacy_id = "ql-guest-1"
    guest.save(update_fields=["legacy_id", "updated_at"])

    defaults = QuotationLoader().transform(
        {
            "Id": "1",
            "ClientDetailsId": "ql-guest-1",
            "AgentId": None,
            "EnquireId": None,
            "QuotationNo": 42,
        }
    )

    assert defaults is not None
    assert defaults["person"] == person_for_guest(guest)


# ---------------------------------------------------------------------------
# link_person_fks delta linker — safety net
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_link_person_fks_links_null_rows_and_is_idempotent(
    quotation_line: QuotationLine,
    terms: TermsVersion,
    guest: Guest,
) -> None:
    # GAP-045 Unit 3d-A made `person` NOT NULL on Quotation/Booking/BookingGuest/
    # GuestPreference, so only Enquiry can still carry a null person (anonymous
    # leads). The delta linker therefore only has real work to do for Enquiry;
    # the other four are no-ops it must not choke on.
    booking = BookingService.create_from_quotation_line(quotation_line, terms_version=terms)
    quotation = quotation_line.quotation
    enquiry = quotation.enquiry

    # Simulate a row written before the inline-setting code shipped: NULL out
    # Enquiry.person via a bulk .update() (bypasses the inline write paths).
    Enquiry.objects.filter(pk=enquiry.pk).update(person=None)

    call_command("link_person_fks")

    expected = person_for_guest(guest)
    enquiry.refresh_from_db()
    assert enquiry.person == expected
    # The always-customer models were already linked at write time and untouched.
    booking.refresh_from_db()
    assert booking.person == expected

    # Second run is a no-op — nothing is NULL anymore.
    call_command("link_person_fks")
    enquiry.refresh_from_db()
    assert enquiry.person == expected
