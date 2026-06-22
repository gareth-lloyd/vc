"""API tests for the Clients (renter) directory list.

`GAP-047`: `GET /api/v1/clients` is a query-pinned list over `accounts.Person`
filtered to `kind=CUSTOMER`, annotated with a booking-channel `is_agent` flag
(any of the customer's enquiries / quotes / bookings names a travel agent).
Hosted from `reservations/urls.py` — `accounts` is the bottom of the import
spine and cannot serialise reservations rows (precedent: `contact_reads.py`).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import CustomerPersonFactory, PersonFactory
from accounts.models import Person, User
from core.enums import StaffRole
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.models import Property
from reservations.enums import PaymentMethod, QuotationStatus
from reservations.models import Booking, Enquiry, Quotation, QuotationLine, TermsVersion


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True, email="staff@example.com", password="x", role=StaffRole.RESERVATIONS
    )


def _customer(**kwargs: object) -> Person:
    return cast(Person, CustomerPersonFactory(**kwargs))


def _agent() -> Person:
    """A business contact used as the `.agent` on a deal."""
    return cast(Person, PersonFactory())


def _agent_quote(*, person: Person, agent: Person, terms: TermsVersion) -> Quotation:
    enquiry = Enquiry.objects.create(person=person, first_name="Q", adults=2)
    return Quotation.objects.create(
        enquiry=enquiry,
        person=person,
        agent=agent,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
        status=QuotationStatus.SENT.value,
    )


def _agent_booking(
    *, person: Person, agent: Person, property_: Property, gbp: Currency, terms: TermsVersion
) -> Booking:
    enquiry = Enquiry.objects.create(person=person, first_name="B", adults=2)
    quote = Quotation.objects.create(
        enquiry=enquiry,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
        status=QuotationStatus.ACCEPTED.value,
    )
    line = QuotationLine.objects.create(
        quotation=quote,
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
        agent=agent,
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
    )


@pytest.mark.django_db
def test_lists_only_customers(api_client: APIClient, staff: User) -> None:
    customer = _customer()
    contact = cast(Person, PersonFactory())  # kind=CONTACT (model default)
    api_client.force_login(staff)

    response = api_client.get("/api/v1/clients")

    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["results"]}
    assert customer.pk in ids
    assert contact.pk not in ids


@pytest.mark.django_db
def test_row_shape_exposes_primary_channels(api_client: APIClient, staff: User) -> None:
    customer = _customer(primary_email="ada@example.com", primary_phone="+44 7700 900111")
    api_client.force_login(staff)

    response = api_client.get("/api/v1/clients")

    row = next(r for r in response.json()["results"] if r["id"] == customer.pk)
    assert row["primary_email"] == "ada@example.com"
    assert row["primary_phone"] == "+44 7700 900111"
    assert row["is_agent"] is False


@pytest.mark.django_db
def test_is_agent_true_via_enquiry(api_client: APIClient, staff: User) -> None:
    customer = _customer()
    Enquiry.objects.create(person=customer, agent=_agent(), first_name="E", adults=2)
    api_client.force_login(staff)

    row = next(
        r for r in api_client.get("/api/v1/clients").json()["results"] if r["id"] == customer.pk
    )
    assert row["is_agent"] is True


@pytest.mark.django_db
def test_is_agent_true_via_quote(api_client: APIClient, staff: User, terms: TermsVersion) -> None:
    customer = _customer()
    _agent_quote(person=customer, agent=_agent(), terms=terms)
    api_client.force_login(staff)

    row = next(
        r for r in api_client.get("/api/v1/clients").json()["results"] if r["id"] == customer.pk
    )
    assert row["is_agent"] is True


@pytest.mark.django_db
def test_is_agent_true_via_booking(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    customer = _customer()
    _agent_booking(person=customer, agent=_agent(), property_=property_, gbp=gbp, terms=terms)
    api_client.force_login(staff)

    row = next(
        r for r in api_client.get("/api/v1/clients").json()["results"] if r["id"] == customer.pk
    )
    assert row["is_agent"] is True


@pytest.mark.django_db
def test_capacity_filter_partitions_direct_and_agent(api_client: APIClient, staff: User) -> None:
    direct = _customer()
    agent_client = _customer()
    Enquiry.objects.create(person=agent_client, agent=_agent(), first_name="E", adults=2)
    api_client.force_login(staff)

    agent_ids = {
        r["id"] for r in api_client.get("/api/v1/clients?capacity=agent").json()["results"]
    }
    direct_ids = {
        r["id"] for r in api_client.get("/api/v1/clients?capacity=direct").json()["results"]
    }

    assert agent_client.pk in agent_ids and direct.pk not in agent_ids
    assert direct.pk in direct_ids and agent_client.pk not in direct_ids


@pytest.mark.django_db
def test_search_matches_name_and_email(api_client: APIClient, staff: User) -> None:
    match = _customer(first_name="Zelda", last_name="Fitz", primary_email="zelda@example.com")
    _customer(first_name="Other", last_name="Person", primary_email="other@example.com")
    api_client.force_login(staff)

    by_name = {r["id"] for r in api_client.get("/api/v1/clients?search=Zelda").json()["results"]}
    by_email = {
        r["id"] for r in api_client.get("/api/v1/clients?search=zelda@example").json()["results"]
    }

    assert by_name == {match.pk}
    assert by_email == {match.pk}


@pytest.mark.django_db
def test_requires_staff(api_client: APIClient) -> None:
    _customer()
    assert api_client.get("/api/v1/clients").status_code in (401, 403)


@pytest.mark.django_db
def test_query_count_is_flat(api_client: APIClient, staff: User, terms: TermsVersion) -> None:
    api_client.force_login(staff)
    _customer()
    with assert_max_queries(8) as one:
        assert api_client.get("/api/v1/clients").status_code == 200

    for _ in range(11):
        c = _customer()
        Enquiry.objects.create(person=c, agent=_agent(), first_name="E", adults=2)
    with assert_max_queries(8) as many:
        assert api_client.get("/api/v1/clients").status_code == 200

    assert len(one.captured_queries) == len(many.captured_queries)
