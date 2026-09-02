"""GAP-089: `PastStay` — the honest minimal record of a historic stay imported
from Nick's spreadsheets (villa + year + booking number, no dates / money).

Surfaces on Customer-360 as "Past stays" and folds into the derived
`is_repeat_customer` flag on both `/contacts/{id}` and `/clients`.
"""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.factories import CustomerPersonFactory
from accounts.models import Person, User
from core.enums import StaffRole
from properties.models import Property
from reservations.models import PastStay

pytestmark = pytest.mark.django_db


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


def _stay(person: Person, **kwargs: object) -> PastStay:
    defaults: dict[str, object] = {"villa_name": "Villa Yeraki", "year": 2019}
    defaults.update(kwargs)
    return PastStay.objects.create(person=person, **defaults)


def test_default_ordering_is_newest_year_first(person: Person) -> None:
    old = _stay(person, year=2017, booking_number="BN10")
    undated = _stay(person, year=None, booking_number="BN99")
    new = _stay(person, year=2023, booking_number="BN500")

    assert list(PastStay.objects.all()) == [new, old, undated]


def test_contact_past_stays_lists_rows_with_optional_property(
    api_client: APIClient, staff: User, person: Person, property_: Property
) -> None:
    linked = _stay(
        person,
        booking_number="BN500",
        villa_name="Test Villa",
        property=property_,
        destination="Corfu",
        year=2023,
    )
    unlinked = _stay(person, booking_number="BN10", villa_name="Villa Unknown", year=2017)
    _stay(cast(Person, CustomerPersonFactory()), booking_number="BN1")  # someone else's
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/contacts/{person.pk}/past-stays")

    assert response.status_code == 200
    rows = response.json()["results"]
    assert [r["id"] for r in rows] == [linked.pk, unlinked.pk]
    assert rows[0] == {
        "id": linked.pk,
        "booking_number": "BN500",
        "villa_name": "Test Villa",
        "property": property_.pk,
        "property_name": "Test Villa",
        "destination": "Corfu",
        "year": 2023,
        "notes": "",
    }
    assert rows[1]["property"] is None
    assert rows[1]["property_name"] is None


def test_contact_past_stays_requires_staff(api_client: APIClient, person: Person) -> None:
    user = User.objects.create_user(is_staff=False, email="owner@example.com", password="x")
    api_client.force_login(user)

    assert api_client.get(f"/api/v1/contacts/{person.pk}/past-stays").status_code == 403


def test_contact_detail_counts_past_stays_as_repeat(
    api_client: APIClient, staff: User, person: Person
) -> None:
    _stay(person)
    _stay(person, year=2021)
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{person.pk}").json()

    assert body["booking_count"] == 0
    assert body["past_stay_count"] == 2
    assert body["is_repeat_customer"] is True


def test_contact_list_past_stay_count_does_not_inflate_booking_count(
    api_client: APIClient, staff: User, person: Person
) -> None:
    # Two annotations over two reverse FKs must not cross-join into a product.
    _stay(person)
    _stay(person, year=2021)
    _stay(person, year=2022)
    api_client.force_login(staff)

    body = api_client.get("/api/v1/contacts").json()

    row = next(r for r in body["results"] if r["id"] == person.pk)
    assert body["count"] == 1
    assert row["past_stay_count"] == 3
    assert row["booking_count"] == 0


def test_clients_list_marks_past_stay_only_client_as_repeat(
    api_client: APIClient, staff: User, person: Person
) -> None:
    _stay(person)
    never = cast(Person, CustomerPersonFactory())
    api_client.force_login(staff)

    results = api_client.get("/api/v1/clients").json()["results"]
    repeat_ids = {r["id"] for r in api_client.get("/api/v1/clients?repeat=true").json()["results"]}

    row = next(r for r in results if r["id"] == person.pk)
    assert row["is_repeat_customer"] is True
    assert person.pk in repeat_ids
    assert never.pk not in repeat_ids


def test_contact_types_treats_a_past_stay_as_having_booked(
    api_client: APIClient, staff: User
) -> None:
    # A non-customer kind with only a sheet stay: `is_repeat_customer` and the
    # CUSTOMER type badge must agree (both derive from "has booked").
    contact = Person.objects.create(first_name="Old", last_name="Guest", kind="contact")
    _stay(contact)
    api_client.force_login(staff)

    body = api_client.get(f"/api/v1/contacts/{contact.pk}").json()

    assert body["is_repeat_customer"] is True
    assert "customer" in body["contact_types"]


def test_anonymize_blanks_past_stay_notes_but_keeps_the_stay(person: Person) -> None:
    stay = _stay(person, notes="CANCELLED\nYear as written: 1905")

    person.anonymize()

    stay.refresh_from_db()
    assert stay.person == person
    assert stay.villa_name == "Villa Yeraki"
    assert stay.notes == ""


def test_person_merge_moves_past_stays(person: Person) -> None:
    target = cast(Person, CustomerPersonFactory())
    stay = _stay(person)

    person.merge(target)

    stay.refresh_from_db()
    assert stay.person == target
    assert not Person.objects.filter(pk=person.pk).exists()
