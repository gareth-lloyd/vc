"""GAP-045 D3-1 — Enquiry/Quotation accept & expose `person` directly.

The SPA holds **Person ids** off `/contacts`. These tests pin the backend
write/read contract:

- writes ACCEPT a `person` id on Enquiry + Quotation;
- reads EXPOSE the `person` id so the SPA can show / navigate to the customer;
- the quote-create service builds a Quotation (and its auto-minted enquiry) from
  a Person.

`person` is the sole customer FK (the legacy `guest` leg was dropped in D5-4c).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.enums import EmailLabel, PersonKind, PhoneLabel
from accounts.models import Person, PersonEmail, PersonPhone, User
from core.enums import StaffRole
from pricing.models import Currency
from properties.models import Property
from reservations.enums import EnquirySource
from reservations.models import Enquiry, Quotation, TermsVersion
from reservations.services.quotations import QuotationService


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="res-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def enquiry(customer: Person) -> Enquiry:
    return Enquiry.objects.create(
        person=customer,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        adults=2,
    )


@pytest.fixture
def quotation(customer: Person, gbp: Currency, terms: TermsVersion) -> Quotation:
    return Quotation.objects.create(
        enquiry=customer.enquiries_as_customer.create(),
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


def _customer(first: str = "Stand", last: str = "Alone") -> Person:
    """A first-class customer Person unrelated to any Guest mirror."""
    person = Person.objects.create(
        first_name=first,
        last_name=last,
        kind=PersonKind.CUSTOMER.value,
    )
    PersonEmail.objects.create(
        contact=person,
        email=f"{first.lower()}@contacts.example.com",
        label=EmailLabel.PRIMARY.value,
        is_primary=True,
    )
    PersonPhone.objects.create(
        contact=person,
        number="+447700900123",
        label=PhoneLabel.MOBILE.value,
        is_primary=True,
    )
    return person


# ---------------------------------------------------------------------------
# Enquiry — accept `person`
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_enquiry_accepts_person(api_client: APIClient, staff: User) -> None:
    person = _customer()
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {"person": person.pk, "adults": 2},
        format="json",
    )

    assert response.status_code == 201, response.data
    enquiry = Enquiry.objects.get()
    assert enquiry.person_id == person.pk


@pytest.mark.django_db
def test_create_enquiry_ignores_unknown_guest_input(api_client: APIClient, staff: User) -> None:
    """GAP-045: `guest` is not a write field — a body sending only a `guest` id
    writes no customer (the unknown key is ignored), leaving person null."""
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {"guest": 999, "adults": 2},
        format="json",
    )

    assert response.status_code == 201, response.data
    enquiry = Enquiry.objects.get()
    assert enquiry.person_id is None


@pytest.mark.django_db
def test_patch_enquiry_repoints_person(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    person = _customer("Re", "Point")
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/enquiries/{enquiry.pk}",
        {"person": person.pk},
        format="json",
    )

    assert response.status_code == 200, response.data
    enquiry.refresh_from_db()
    assert enquiry.person_id == person.pk


@pytest.mark.django_db
def test_enquiry_detail_exposes_person(
    api_client: APIClient, staff: User, enquiry: Enquiry
) -> None:
    person = _customer("Read", "Back")
    enquiry.person = person
    enquiry.save(update_fields=["person"])
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/enquiries/{enquiry.pk}")

    assert response.status_code == 200, response.data
    assert response.data["person"] == person.pk


# ---------------------------------------------------------------------------
# Quotation — accept `person`
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_quotation_accepts_person(
    api_client: APIClient, staff: User, gbp: Currency, terms: TermsVersion
) -> None:
    person = _customer("Quote", "Cust")
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/quotations",
        {
            "person": person.pk,
            "currency": gbp.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    quotation = Quotation.objects.get()
    assert quotation.person_id == person.pk


@pytest.mark.django_db
def test_create_quotation_ignores_unknown_guest_field(
    api_client: APIClient, staff: User, gbp: Currency, terms: TermsVersion
) -> None:
    """GAP-045: the quotation write serializer does not accept `guest` — a stray
    `guest` id in the body is ignored; only `person` drives the customer."""
    person = _customer("Q", "Win")
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/quotations",
        {
            "person": person.pk,
            "guest": 999,
            "currency": gbp.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    quotation = Quotation.objects.get()
    assert quotation.person_id == person.pk


@pytest.mark.django_db
def test_create_quotation_without_customer_is_400(
    api_client: APIClient, staff: User, terms: TermsVersion
) -> None:
    """`Quotation.person` is NOT NULL — a create with no person/guest is a clean
    400, not a leaked DB IntegrityError (500)."""
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/quotations",
        {
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "person" in response.data["field_errors"]


@pytest.mark.django_db
def test_quotation_detail_exposes_person(
    api_client: APIClient, staff: User, quotation: Quotation
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/quotations/{quotation.pk}")

    assert response.status_code == 200, response.data
    assert response.data["person"] == quotation.person_id


@pytest.mark.django_db
def test_agent_direct_quote_from_person_mints_enquiry(
    api_client: APIClient,
    staff: User,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: object,
) -> None:
    """No enquiry + a `person` id → the service mints the AGENT_PORTAL enquiry
    from the Person (display name / primary email / preferred method)."""
    person = _customer("Agent", "Direct")
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/quotations",
        {
            "person": person.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
            "lines": [
                {
                    "property": property_.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 2,
                    "children": 0,
                },
            ],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    quotation = Quotation.objects.get()
    assert quotation.person_id == person.pk
    enquiry = quotation.enquiry
    assert enquiry is not None
    assert enquiry.person_id == person.pk
    assert enquiry.site_source == EnquirySource.AGENT_PORTAL.value
    assert enquiry.email == person.primary_email()


# ---------------------------------------------------------------------------
# Service-level — minimal_enquiry_for seeds from the Person
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_minimal_enquiry_for_seeds_from_person() -> None:
    person = _customer("Seed", "Ed")

    enquiry = QuotationService.minimal_enquiry_for(person)

    assert enquiry.person_id == person.pk
    assert enquiry.first_name == person.first_name
    assert enquiry.last_name == person.last_name
    assert enquiry.email == person.primary_email()
    assert enquiry.phone == person.primary_phone()
    assert enquiry.contact_method == person.preferred_method
    assert enquiry.site_source == EnquirySource.AGENT_PORTAL.value
