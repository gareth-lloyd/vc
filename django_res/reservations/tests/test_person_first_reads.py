"""GAP-045 — staff-API reads resolve customer data from the unified Person.

Every staff-API read of a customer's name / email / phone resolves from the
linked ``accounts.Person``. These tests build a customer Person, point the
reservation rows at it, and assert the API returns the Person's name / email /
phone — and that the multi-valued email child can't inflate the paginator COUNT
or the per-list query budget.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import CustomerPersonFactory
from accounts.models import Person, User
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.models import Property
from reservations.models import Booking, Enquiry, Quotation, QuotationLine, TermsVersion
from reservations.serializers.availability import AvailabilityBookingSerializer
from reservations.serializers.concierge_overview import ConciergeOverviewSerializer


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


@pytest.fixture
def customer(db: None) -> Person:
    """A CUSTOMER Person with name + primary email + primary phone set."""
    return cast(
        Person,
        CustomerPersonFactory(
            first_name="Grace",
            last_name="Hopper",
            primary_email="grace@navy.mil",
            primary_phone="+15125550100",
        ),
    )


def _booking_with_person(
    person: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    *,
    status: str = "awaiting_deposit",
    day_offset: int = 0,
) -> Booking:
    quotation = Quotation.objects.create(
        enquiry=Enquiry.objects.create(person=person),
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
def test_person_primary_helpers_read_prefetch_cache(customer: Person) -> None:
    assert customer.display_name == "Grace Hopper"
    assert customer.primary_email() == "grace@navy.mil"
    assert customer.primary_phone() == "+15125550100"


@pytest.mark.django_db
def test_person_display_name_blank_when_no_name() -> None:
    person = Person.objects.create(first_name="", last_name="")
    assert person.display_name is None


@pytest.mark.django_db
def test_person_primary_email_falls_back_to_oldest_when_none_flagged(customer: Person) -> None:
    # Drop the is_primary flag so the oldest-by-pk fallback path is exercised.
    customer.emails.update(is_primary=False)
    person = Person.objects.prefetch_related("emails").get(pk=customer.pk)
    assert person.primary_email() == "grace@navy.mil"


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_booking_list_reads_person_name_and_email(
    api_client: APIClient,
    staff: User,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(customer, gbp, terms, property_)

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
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(customer, gbp, terms, property_)

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}")

    assert response.status_code == 200
    assert response.data["guest_name"] == "Grace Hopper"
    assert response.data["guest_email"] == "grace@navy.mil"


# ---------------------------------------------------------------------------
# Quotation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_quotation_list_reads_person_name(
    api_client: APIClient,
    staff: User,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    _booking_with_person(customer, gbp, terms, property_)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/quotations")

    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["guest_name"] == "Grace Hopper"


# ---------------------------------------------------------------------------
# Enquiry — person → enquiry-own denorm fallback
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_enquiry_list_reads_person_name_email_phone(
    api_client: APIClient,
    staff: User,
    customer: Person,
    property_: Property,
) -> None:
    enquiry = Enquiry.objects.create(person=customer, property=property_)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/enquiries")

    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["id"] == enquiry.pk)
    assert row["guest_name"] == "Grace Hopper"
    assert row["guest_email"] == "grace@navy.mil"
    assert row["guest_phone"] == "+15125550100"


@pytest.mark.django_db
def test_enquiry_with_person_serialises_name_email_phone(
    api_client: APIClient,
    staff: User,
    customer: Person,
    property_: Property,
) -> None:
    """Person is the sole source: an enquiry with the Person set serialises the
    person's name / email / phone / preferred method."""
    enquiry = Enquiry.objects.create(person=customer, property=property_)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/enquiries")

    assert response.status_code == 200
    row = next(r for r in response.data["results"] if r["id"] == enquiry.pk)
    assert row["guest_name"] == "Grace Hopper"
    assert row["guest_email"] == "grace@navy.mil"
    assert row["guest_phone"] == "+15125550100"
    # contact_method resolves solely from the Person.
    assert row["guest_contact_method"] == customer.preferred_method


@pytest.mark.django_db
def test_enquiry_name_falls_back_to_denorm_when_no_person(
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
def test_enquiry_contact_method_reads_person_preferred_method(
    api_client: APIClient,
    staff: User,
    property_: Property,
) -> None:
    """GAP-045: contact_method resolves from the Person's ``preferred_method``.
    A customer Person defaults to "email"."""
    person = cast(
        Person,
        CustomerPersonFactory(first_name="No", last_name="Method", primary_email="nm@example.com"),
    )
    assert person.preferred_method == "email"
    enquiry = Enquiry.objects.create(person=person, property=property_)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/enquiries")

    row = next(r for r in response.data["results"] if r["id"] == enquiry.pk)
    assert row["guest_contact_method"] == "email"


# ---------------------------------------------------------------------------
# Availability + concierge (serializer-level — both name-only)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_availability_serializer_reads_person_name(
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(customer, gbp, terms, property_)
    fresh = Booking.objects.select_related("person").get(pk=booking.pk)
    assert AvailabilityBookingSerializer(fresh).data["guest_name"] == "Grace Hopper"


@pytest.mark.django_db
def test_concierge_serializer_reads_person_name(
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(customer, gbp, terms, property_)
    fresh = Booking.objects.select_related("person").get(pk=booking.pk)
    data = ConciergeOverviewSerializer(fresh, context={"today": date(2026, 6, 1)}).data
    assert data["guest_name"] == "Grace Hopper"


# ---------------------------------------------------------------------------
# Quotation render seam (3c-2b) — customer email/PDF name resolves person-first
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_quotation_render_context_reads_person_name(
    customer: Person,
    terms: TermsVersion,
) -> None:
    from reservations.services.quotation_render import build_quotation_context

    quotation = Quotation.objects.create(
        enquiry=Enquiry.objects.create(person=customer),
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    fresh = Quotation.objects.select_related("person").get(pk=quotation.pk)

    ctx = build_quotation_context(fresh)

    assert ctx["guest_first_name"] == "Grace"
    assert ctx["guest_full_name"] == "Grace Hopper"


# ---------------------------------------------------------------------------
# BookingFilter — person search + no COUNT inflation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_booking_search_matches_person_name(
    api_client: APIClient,
    staff: User,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(customer, gbp, terms, property_)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/bookings", {"q": "Hopper"})

    assert response.status_code == 200
    assert [r["id"] for r in response.data["results"]] == [booking.pk]


@pytest.mark.django_db
def test_booking_search_matches_person_email_without_inflating_count(
    api_client: APIClient,
    staff: User,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Person email lives in a multi-valued child table; the filter matches it
    via ``Exists()`` so the paginator COUNT stays at one row, not one row per
    PersonEmail (the LEFT-JOIN inflation django_res/CLAUDE.md warns about)."""
    booking = _booking_with_person(customer, gbp, terms, property_)
    # A second email on the same person would multiply rows under a join-based
    # OR; under Exists() it must not.
    customer.emails.create(email="grace2@navy.mil", is_primary=False)

    api_client.force_login(staff)
    response = api_client.get("/api/v1/bookings", {"q": "grace@navy.mil"})

    assert response.status_code == 200
    assert response.data["count"] == 1
    assert [r["id"] for r in response.data["results"]] == [booking.pk]


@pytest.mark.django_db
def test_booking_status_counts_not_inflated_by_person_emails(
    api_client: APIClient,
    staff: User,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    booking = _booking_with_person(customer, gbp, terms, property_)
    customer.emails.create(email="grace2@navy.mil", is_primary=False)
    customer.emails.create(email="grace3@navy.mil", is_primary=False)

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
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Adding more person-linked bookings must not grow the query count — the
    person join + email prefetch keep the list at a constant budget."""
    for i in range(3):
        extra = cast(
            Person,
            CustomerPersonFactory(
                first_name="Extra",
                last_name="Guest",
                primary_email=f"extra{i}@example.com",
            ),
        )
        _booking_with_person(extra, gbp, terms, property_, day_offset=i + 1)
    _booking_with_person(customer, gbp, terms, property_, day_offset=0)

    api_client.force_login(staff)
    api_client.get("/api/v1/bookings")  # warm caches

    with assert_max_queries(10):
        response = api_client.get("/api/v1/bookings")
    assert response.status_code == 200
    assert response.data["count"] == 4
