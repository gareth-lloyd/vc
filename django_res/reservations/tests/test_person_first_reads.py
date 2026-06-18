"""GAP-045 Unit 3c-2a — staff-API reads resolve from the unified Person.

Every staff-API read of a customer's name / email / phone now resolves from
the linked ``accounts.Person`` mirror first, falling back to the legacy
``reservations.Guest`` columns while ``person`` is still null. These tests
edit the Person so its values *differ* from the originating Guest, then assert
the API returns the Person's values — proving the read switched source, not
just that the (identical) mirror happens to agree.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.enums import PhoneLabel
from accounts.models import Person, PersonPhone, User
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.models import Property
from reservations.models import Booking, Enquiry, Guest, Quotation, QuotationLine, TermsVersion
from reservations.serializers.availability import AvailabilityBookingSerializer
from reservations.serializers.concierge_overview import ConciergeOverviewSerializer
from reservations.services.person_sync import person_for_guest


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="pfr-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


def _repoint_person(guest: Guest) -> Person:
    """Edit the Person mirror so its name / email / phone differ from the Guest.

    Simulates a staff edit to the unified record after the Guest was linked —
    the whole point of Person becoming the read source. Returns the edited
    Person (always non-null — ``person_for_guest`` creates it if missing).
    """
    person = person_for_guest(guest)
    person.first_name = "Grace"
    person.last_name = "Hopper"
    person.save(update_fields=["first_name", "last_name", "updated_at"])
    primary_email = person.emails.filter(is_primary=True).first()
    assert primary_email is not None
    primary_email.email = "grace@navy.mil"
    primary_email.save(update_fields=["email", "updated_at"])
    PersonPhone.objects.create(
        contact=person,
        number="+15125550100",
        label=PhoneLabel.MOBILE.value,
        is_primary=True,
    )
    return person


def _booking_with_person(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    *,
    status: str = "awaiting_deposit",
    day_offset: int = 0,
) -> Booking:
    person = person_for_guest(guest)
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(person=person),
        guest=guest,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10) + timedelta(days=day_offset * 30),
        date_to=date(2026, 6, 17) + timedelta(days=day_offset * 30),
        adults=2,
        total=Decimal("1400.00"),
    )
    booking = Booking.objects.create(
        quotation_line=line,
        guest=guest,
        person=person,
        property=property_,
        date_from=line.date_from,
        date_to=line.date_to,
        adults=line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method="card",
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        status=status,
    )
    return booking


# ---------------------------------------------------------------------------
# Person model helpers
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_person_primary_helpers_read_prefetch_cache(guest: Guest) -> None:
    person = person_for_guest(guest)
    PersonPhone.objects.create(
        contact=person, number="+15125550100", label=PhoneLabel.MOBILE.value, is_primary=True
    )
    assert person.display_name == "Ada Lovelace"
    assert person.primary_email() == "ada@example.com"
    assert person.primary_phone() == "+15125550100"


@pytest.mark.django_db
def test_person_display_name_blank_when_no_name() -> None:
    person = Person.objects.create(first_name="", last_name="")
    assert person.display_name is None


@pytest.mark.django_db
def test_person_primary_email_falls_back_to_oldest_when_none_flagged(guest: Guest) -> None:
    person = person_for_guest(guest)
    # Drop the is_primary flag so the oldest-by-pk fallback path is exercised.
    person.emails.update(is_primary=False)
    person = Person.objects.prefetch_related("emails").get(pk=person.pk)
    assert person.primary_email() == "ada@example.com"


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_booking_list_reads_person_name_and_email(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(guest, gbp, terms, property_)
    _repoint_person(guest)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/bookings")

    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["id"] == booking.pk)
    assert row["guest_name"] == "Grace Hopper"
    assert row["guest_email"] == "grace@navy.mil"


@pytest.mark.django_db
def test_booking_detail_reads_person_name_and_email(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(guest, gbp, terms, property_)
    _repoint_person(guest)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["guest_name"] == "Grace Hopper"
    assert response.data["guest_email"] == "grace@navy.mil"


@pytest.mark.django_db
def test_booking_falls_back_to_guest_when_person_null(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(guest, gbp, terms, property_)
    Booking.objects.filter(pk=booking.pk).update(person=None)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["guest_name"] == "Ada Lovelace"
    assert response.data["guest_email"] == "ada@example.com"


# ---------------------------------------------------------------------------
# Quotation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_quotation_list_reads_person_name(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    _booking_with_person(guest, gbp, terms, property_)
    _repoint_person(guest)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/quotations")

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["guest_name"] == "Grace Hopper"


# ---------------------------------------------------------------------------
# Enquiry — triple fallback (person → guest → enquiry-own denorm)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_enquiry_list_reads_person_name_email_phone(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    property_: Property,
) -> None:
    person = person_for_guest(guest)
    enquiry = Enquiry.objects.create(guest=guest, person=person, property=property_)
    _repoint_person(guest)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/enquiries")

    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["id"] == enquiry.pk)
    assert row["guest_name"] == "Grace Hopper"
    assert row["guest_email"] == "grace@navy.mil"
    assert row["guest_phone"] == "+15125550100"


@pytest.mark.django_db
def test_enquiry_name_falls_back_to_denorm_when_no_person_or_guest(
    api_client: APIClient,
    staff: User,
    property_: Property,
) -> None:
    enquiry = Enquiry.objects.create(
        property=property_,
        first_name="Anon",
        last_name="Lead",
        email="anon@example.com",
    )

    api_client.force_login(staff)
    response = api_client.get("/api/v1/enquiries")

    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["id"] == enquiry.pk)
    assert row["guest_name"] == "Anon Lead"


@pytest.mark.django_db
def test_enquiry_contact_method_stays_guest_sourced(
    api_client: APIClient,
    staff: User,
    property_: Property,
) -> None:
    """A guest with no contact_method must report null — NOT the "email" the
    Person mirror defaults its ``preferred_method`` to (the 3c-2a decision)."""
    guest = Guest.objects.create(first_name="No", last_name="Method", email="nm@example.com")
    person = person_for_guest(guest)
    assert person.preferred_method == "email"  # mirror coerced null → email
    enquiry = Enquiry.objects.create(guest=guest, person=person, property=property_)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/enquiries")

    row = next(r for r in response.data["results"] if r["id"] == enquiry.pk)
    assert row["guest_contact_method"] is None


# ---------------------------------------------------------------------------
# Availability + concierge (serializer-level — both name-only)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_availability_serializer_reads_person_name(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(guest, gbp, terms, property_)
    _repoint_person(guest)
    fresh = Booking.objects.select_related("guest", "person").get(pk=booking.pk)
    assert AvailabilityBookingSerializer(fresh).data["guest_name"] == "Grace Hopper"


@pytest.mark.django_db
def test_concierge_serializer_reads_person_name(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(guest, gbp, terms, property_)
    _repoint_person(guest)
    fresh = Booking.objects.select_related("guest", "person").get(pk=booking.pk)
    data = ConciergeOverviewSerializer(fresh, context={"today": date(2026, 6, 1)}).data
    assert data["guest_name"] == "Grace Hopper"


# ---------------------------------------------------------------------------
# Quotation render seam (3c-2b) — customer email/PDF name resolves person-first
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_quotation_render_context_reads_person_name(
    guest: Guest,
    terms: TermsVersion,
) -> None:
    from reservations.services.quotation_render import build_quotation_context

    person = person_for_guest(guest)
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(person=person),
        guest=guest,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    _repoint_person(guest)
    # Re-fetch so the seam reads the repointed Person, not the stale instance
    # cached on the in-memory quotation (the live send loads it fresh).
    fresh = Quotation.objects.select_related("person", "guest").get(pk=quotation.pk)

    ctx = build_quotation_context(fresh)

    assert ctx["guest_first_name"] == "Grace"
    assert ctx["guest_full_name"] == "Grace Hopper"


@pytest.mark.django_db
def test_quotation_render_context_falls_back_to_guest_when_person_null(
    guest: Guest,
    terms: TermsVersion,
) -> None:
    from reservations.services.quotation_render import build_quotation_context

    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )

    ctx = build_quotation_context(quotation)

    assert ctx["guest_first_name"] == "Ada"
    assert ctx["guest_full_name"] == "Ada Lovelace"


# ---------------------------------------------------------------------------
# BookingFilter — person search + no COUNT inflation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_booking_search_matches_person_name(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(guest, gbp, terms, property_)
    _repoint_person(guest)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/bookings", {"q": "Hopper"})

    assert response.status_code == 200
    assert [r["id"] for r in response.data["results"]] == [booking.pk]


@pytest.mark.django_db
def test_booking_search_matches_person_email_without_inflating_count(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Person email lives in a multi-valued child table; the filter matches it
    via ``Exists()`` so the paginator COUNT stays at one row, not one row per
    PersonEmail (the LEFT-JOIN inflation django_res/CLAUDE.md warns about)."""
    booking = _booking_with_person(guest, gbp, terms, property_)
    person = _repoint_person(guest)
    # A second email on the same person would multiply rows under a join-based
    # OR; under Exists() it must not.
    person.emails.create(email="grace2@navy.mil", is_primary=False)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/bookings", {"q": "grace@navy.mil"})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert [r["id"] for r in response.data["results"]] == [booking.pk]


@pytest.mark.django_db
def test_booking_status_counts_not_inflated_by_person_emails(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(guest, gbp, terms, property_)
    person = _repoint_person(guest)
    person.emails.create(email="grace2@navy.mil", is_primary=False)
    person.emails.create(email="grace3@navy.mil", is_primary=False)

    api_client.force_login(staff)
    # Unfiltered: the booking is counted once, not once per PersonEmail.
    response = api_client.get("/api/v1/bookings/status-counts")
    assert response.status_code == 200
    assert response.data == {booking.status: 1}

    # And a person-email search (the Exists() branch) also counts it once.
    searched = api_client.get("/api/v1/bookings/status-counts", {"q": "grace@navy.mil"})
    assert searched.data == {booking.status: 1}


@pytest.mark.django_db
def test_booking_list_person_reads_stay_within_query_budget(
    api_client: APIClient,
    staff: User,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Adding more person-linked bookings must not grow the query count — the
    person join + email prefetch keep the list at a constant budget."""
    for i in range(3):
        g = Guest.objects.create(
            first_name="Extra", last_name="Guest", email=f"extra{i}@example.com"
        )
        _booking_with_person(g, gbp, terms, property_, day_offset=i + 1)
    _booking_with_person(guest, gbp, terms, property_, day_offset=0)

    api_client.force_login(staff)
    api_client.get("/api/v1/bookings")  # warm caches

    with assert_max_queries(10):
        response = api_client.get("/api/v1/bookings")
    assert response.status_code == 200
    assert response.data["count"] == 4
