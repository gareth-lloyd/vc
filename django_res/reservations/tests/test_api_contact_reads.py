"""API tests for the Person-scoped customer history reads.

`GAP-045` Unit 3d-1: `/contacts/{id}/bookings|enquiries|quotations|
travel-preferences` key on the unified `accounts.Person`. Hosted from
`reservations/urls.py` (a downward reservations → accounts edge).
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
from reservations.enums import PaymentMethod, QuotationStatus
from reservations.models import (
    Booking,
    Enquiry,
    GuestPreference,
    GuestPreferenceType,
    Quotation,
    QuotationLine,
    TermsVersion,
)


def _quote(
    *,
    enquiry: Enquiry,
    person: Person,
    terms: TermsVersion,
    status: str = QuotationStatus.DRAFT.value,
    legacy_id: str | None = None,
) -> Quotation:
    return Quotation.objects.create(
        enquiry=enquiry,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
        status=status,
        legacy_id=legacy_id,
    )


def _booking_for(
    *,
    quotation: Quotation,
    person: Person,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
    is_archived: bool = False,
) -> Booking:
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        children=0,
        total=Decimal("1400.00"),
        is_selected=True,
    )
    return Booking.objects.create(
        quotation_line=line,
        person=person,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
        is_archived=is_archived,
    )


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True, email="staff@example.com", password="x", role=StaffRole.RESERVATIONS
    )


@pytest.fixture
def person(db: None) -> Person:
    return cast(Person, CustomerPersonFactory())


@pytest.mark.django_db
def test_contact_bookings_returns_linked_rows(
    api_client: APIClient,
    staff: User,
    person: Person,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    enquiry = Enquiry.objects.create(person=person, first_name="Ada", adults=2)
    quote = _quote(enquiry=enquiry, person=person, terms=terms)
    booking = _booking_for(
        quotation=quote, person=person, property_=property_, gbp=gbp, terms=terms
    )
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/contacts/{person.pk}/bookings")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert ids == {booking.pk}


@pytest.mark.django_db
def test_contact_detail_marks_repeat_customer(
    api_client: APIClient,
    staff: User,
    person: Person,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    # GAP-042: the customer-360 profile derives a property-agnostic "Repeat"
    # badge from the person's booking count.
    enquiry = Enquiry.objects.create(person=person, first_name="Ada", adults=2)
    quote = _quote(enquiry=enquiry, person=person, terms=terms)
    _booking_for(quotation=quote, person=person, property_=property_, gbp=gbp, terms=terms)
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{person.pk}").json()

    assert body["booking_count"] == 1
    assert body["is_repeat_customer"] is True


@pytest.mark.django_db
def test_contact_enquiries_includes_quote_count_and_converted_booking(
    api_client: APIClient,
    staff: User,
    person: Person,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    enquiry = Enquiry.objects.create(person=person, first_name="Ada", adults=2)
    _quote(
        enquiry=enquiry,
        person=person,
        terms=terms,
        status=QuotationStatus.CANCELLED.value,
    )
    accepted = _quote(
        enquiry=enquiry,
        person=person,
        terms=terms,
        status=QuotationStatus.ACCEPTED.value,
    )
    booking = _booking_for(
        quotation=accepted, person=person, property_=property_, gbp=gbp, terms=terms
    )
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/contacts/{person.pk}/enquiries")

    assert response.status_code == 200
    row = next(r for r in response.json()["results"] if r["id"] == enquiry.pk)
    assert row["quote_count"] == 2
    assert row["converted_booking"]["reference"] == booking.reference
    # FE links the converted-booking chip to /bookings/:id — needs the pk.
    assert row["converted_booking"]["id"] == booking.pk


@pytest.mark.django_db
def test_contact_quotations_excludes_legacy_synthetic_rows(
    api_client: APIClient,
    staff: User,
    person: Person,
    terms: TermsVersion,
) -> None:
    enquiry = Enquiry.objects.create(person=person, first_name="Ada", adults=2)
    real = _quote(enquiry=enquiry, person=person, terms=terms)
    _quote(enquiry=enquiry, person=person, terms=terms, legacy_id="booking-9999")
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/contacts/{person.pk}/quotations")

    assert response.status_code == 200
    refs = {row["reference"] for row in response.json()["results"]}
    assert refs == {real.reference}


@pytest.mark.django_db
def test_contact_travel_preferences_returns_type_and_notes(
    api_client: APIClient,
    staff: User,
    person: Person,
) -> None:
    pref_type = GuestPreferenceType.objects.create(name="Dietary")
    GuestPreference.objects.create(person=person, preference_type=pref_type, notes="No nuts")
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/contacts/{person.pk}/travel-preferences")

    assert response.status_code == 200
    rows = response.json()["results"]
    assert len(rows) == 1
    assert rows[0]["preference_type"] == "Dietary"
    assert rows[0]["notes"] == "No nuts"


@pytest.mark.django_db
def test_contact_reads_require_staff(
    api_client: APIClient,
    person: Person,
) -> None:
    response = api_client.get(f"/api/v1/contacts/{person.pk}/bookings")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_contact_enquiries_query_count_bounded(
    api_client: APIClient,
    staff: User,
    person: Person,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    """The 3-level quote-stack prefetch keeps the read query-bounded regardless
    of how many enquiries/quotations/bookings hang off the person."""
    for _ in range(4):
        enquiry = Enquiry.objects.create(person=person, first_name="Ada", adults=2)
        accepted = _quote(
            enquiry=enquiry,
            person=person,
            terms=terms,
            status=QuotationStatus.ACCEPTED.value,
        )
        _booking_for(
            quotation=accepted,
            person=person,
            property_=property_,
            gbp=gbp,
            terms=terms,
        )
    api_client.force_login(staff)

    with assert_max_queries(12):
        response = api_client.get(f"/api/v1/contacts/{person.pk}/enquiries")
    assert response.status_code == 200
