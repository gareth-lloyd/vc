"""GAP-045 D3-1 — Enquiry/Quotation accept & expose `person` directly.

The SPA migrates off `/guests` onto `/contacts`, so it holds **Person ids**, not
Guest ids. These tests pin the backend write/read contract that migration needs:

- writes ACCEPT a `person` id on Enquiry + Quotation (precedence person > guest;
  `guest` stays a transitional input the loaders/legacy callers still use);
- reads EXPOSE the `person` id so the SPA can show / navigate to the customer;
- the quote-create service builds a Quotation (and its auto-minted enquiry) from
  a Person, with no Guest in play.

`guest` is removed entirely in D4/D5; until then both legs are accepted.
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
from reservations.models import Enquiry, Guest, Quotation, TermsVersion
from reservations.services.person_sync import person_for_guest
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
def enquiry(guest: Guest) -> Enquiry:
    return Enquiry.objects.create(
        guest=guest,
        person=person_for_guest(guest),
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
        adults=2,
    )


@pytest.fixture
def quotation(guest: Guest, gbp: Currency, terms: TermsVersion) -> Quotation:
    person = person_for_guest(guest)
    return Quotation.objects.create(
        enquiry=guest.enquiries.create(person=person),
        person=person,
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
    # `person` is the sole persisted customer leg — no guest written.
    assert enquiry.guest_id is None


@pytest.mark.django_db
def test_create_enquiry_ignores_guest_input(
    api_client: APIClient, staff: User, guest: Guest
) -> None:
    """GAP-045 D5-2: `guest` is no longer a write field — a body sending only a
    `guest` id writes no customer (it's silently ignored), leaving person null."""
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/enquiries",
        {"guest": guest.pk, "adults": 2},
        format="json",
    )

    assert response.status_code == 201, response.data
    enquiry = Enquiry.objects.get()
    assert enquiry.person_id is None
    assert enquiry.guest_id is None


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
    assert quotation.guest_id is None


@pytest.mark.django_db
def test_create_quotation_ignores_guest_field(
    api_client: APIClient, staff: User, guest: Guest, gbp: Currency, terms: TermsVersion
) -> None:
    """GAP-045 D5-2: the quotation write serializer no longer accepts `guest` —
    a `guest` id in the body is ignored; only `person` drives the customer."""
    person = _customer("Q", "Win")
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/quotations",
        {
            "person": person.pk,
            "guest": guest.pk,
            "currency": gbp.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    quotation = Quotation.objects.get()
    assert quotation.person_id == person.pk
    assert quotation.person_id != person_for_guest(guest).pk


@pytest.mark.django_db
def test_create_quotation_guest_only_is_400(
    api_client: APIClient, staff: User, guest: Guest, gbp: Currency, terms: TermsVersion
) -> None:
    """GAP-045 D5-2: `guest` is no longer resolved — a create carrying only a
    `guest` (no `person`) is rejected with a clean 400, not silently accepted."""
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/quotations",
        {
            "guest": guest.pk,
            "currency": gbp.pk,
            "expires_at": (timezone.now() + timedelta(days=7)).isoformat(),
            "terms_version": terms.pk,
        },
        format="json",
    )

    assert response.status_code == 400, response.data
    assert "person" in response.data["field_errors"]
    assert not Quotation.objects.exists()


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
    from the Person (display name / primary email / preferred method), with no
    Guest anywhere."""
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
    assert quotation.guest_id is None
    enquiry = quotation.enquiry
    assert enquiry is not None
    assert enquiry.person_id == person.pk
    assert enquiry.guest_id is None
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
    assert enquiry.guest_id is None
    assert enquiry.first_name == person.first_name
    assert enquiry.last_name == person.last_name
    assert enquiry.email == person.primary_email()
    assert enquiry.phone == person.primary_phone()
    assert enquiry.contact_method == person.preferred_method
    assert enquiry.site_source == EnquirySource.AGENT_PORTAL.value
