"""Tests for the Person → Zoho Flow contact payload builder (GAP-081)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

import pytest

from accounts.enums import PersonTag, PhoneLabel
from accounts.factories import PersonFactory
from accounts.models import Organisation, Person, PersonEmail, PersonPhone
from integrations.services import zoho_payloads
from integrations.services.zoho_payloads import SENSITIVE_TAGS, build_person_payload
from properties.models.geo import Country

pytestmark = pytest.mark.django_db


def _person(**kwargs: Any) -> Person:
    return cast(Person, PersonFactory(**kwargs))


@pytest.fixture
def country() -> Country:
    # Migration-seeded canonical countries: always get_or_create by iso2.
    country, _ = Country.objects.get_or_create(
        iso2="GB", defaults={"name": "United Kingdom", "iso3": "GBR"}
    )
    return country


@pytest.fixture
def full_person(country: Country) -> Person:
    agency = Organisation.objects.create(name="Acme Travel", country=country)
    person = _person(
        title="Mr",
        first_name="Alan",
        last_name="Partridge",
        agency=agency,
        website_url="https://example.com",
        address_line_1="1 High Street",
        address_line_2="Flat 2",
        town="Norwich",
        post_code="NR1 1AA",
        country=country,
        marketing_consent=True,
        tags=[
            PersonTag.VIP.value,
            PersonTag.DISABILITY.value,
            PersonTag.APPROACH_WITH_CARE.value,
        ],
        notes="private operator notes",
    )
    PersonEmail.objects.create(contact=person, email="alan@example.com", is_primary=True)
    PersonEmail.objects.create(contact=person, email="ap@work.example.com")
    PersonPhone.objects.create(
        contact=person,
        number="+447700900001",
        label=PhoneLabel.MOBILE,
        is_primary=True,
    )
    PersonPhone.objects.create(contact=person, number="+441603123456", label=PhoneLabel.WORK)
    return person


def test_payload_has_res_id_and_id(full_person: Person) -> None:
    payload = build_person_payload(full_person)
    assert payload["RES_ID"] == full_person.pk
    assert payload["id"] == full_person.pk


def test_payload_nests_country_and_agency_with_res_ids(full_person: Person) -> None:
    payload = build_person_payload(full_person)

    country = payload["country"]
    assert country["RES_ID"] == full_person.country_id
    assert country["iso2"] == "GB"
    assert country["name"]

    agency = payload["agency"]
    assert agency["RES_ID"] == full_person.agency_id
    assert agency["name"] == "Acme Travel"
    assert agency["country"]["iso2"] == "GB"


def test_payload_carries_all_emails_and_phones_with_primary_flagged(
    full_person: Person,
) -> None:
    payload = build_person_payload(full_person)

    emails = payload["emails"]
    assert {e["email"] for e in emails} == {"alan@example.com", "ap@work.example.com"}
    assert [e["email"] for e in emails if e["is_primary"]] == ["alan@example.com"]
    assert all("RES_ID" in e for e in emails)

    phones = payload["phones"]
    assert {p["number"] for p in phones} == {"+447700900001", "+441603123456"}
    assert [p["number"] for p in phones if p["is_primary"]] == ["+447700900001"]
    assert all("RES_ID" in p for p in phones)

    assert payload["primary_email"] == "alan@example.com"
    assert payload["primary_phone"] == "+447700900001"
    assert payload["mobile"] == "+447700900001"


def test_payload_pushes_all_tags_while_denylist_is_empty(full_person: Person) -> None:
    payload = build_person_payload(full_person)
    assert set(payload["tags"]) == {
        PersonTag.VIP.value,
        PersonTag.DISABILITY.value,
        PersonTag.APPROACH_WITH_CARE.value,
    }


def test_denylist_mechanism_filters_tags_when_populated(
    full_person: Person, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(zoho_payloads, "SENSITIVE_TAGS", frozenset({PersonTag.DISABILITY.value}))
    payload = build_person_payload(full_person)
    assert set(payload["tags"]) == {
        PersonTag.VIP.value,
        PersonTag.APPROACH_WITH_CARE.value,
    }


def test_payload_includes_notes(full_person: Person) -> None:
    payload = build_person_payload(full_person)
    assert payload["notes"] == "private operator notes"


def test_payload_json_round_trips(full_person: Person) -> None:
    payload = build_person_payload(full_person)
    assert json.loads(json.dumps(payload)) == payload


def test_payload_covers_zoho_contact_post_data_minimums(full_person: Person) -> None:
    """`ZohoContactPostData` (legacy zoho-crm.md): id, RES_ID, Email,
    First_Name, Last_Name, Full_Name, Phone, Title, Mobile, Address_Line_1 —
    mapped to the current `accounts.Person` field names."""
    payload = build_person_payload(full_person)
    minimum = {
        "id",
        "RES_ID",
        "primary_email",  # Email
        "first_name",  # First_Name
        "last_name",  # Last_Name
        "full_name",  # Full_Name
        "primary_phone",  # Phone
        "title",  # Title
        "mobile",  # Mobile
        "address_line_1",  # Address_Line_1
    }
    assert minimum <= payload.keys()
    assert payload["full_name"] == "Alan Partridge"
    assert payload["title"] == "Mr"
    assert payload["address_line_1"] == "1 High Street"


def test_payload_handles_bare_person() -> None:
    person = _person(first_name="Solo", last_name="")
    payload = build_person_payload(person)

    assert payload["agency"] is None
    assert payload["country"] is None
    assert payload["emails"] == []
    assert payload["phones"] == []
    assert payload["primary_email"] is None
    assert payload["primary_phone"] is None
    assert payload["mobile"] is None
    assert json.loads(json.dumps(payload)) == payload


def test_payload_timestamps_are_iso_strings(full_person: Person) -> None:
    payload = build_person_payload(full_person)
    assert isinstance(payload["created_at"], str)
    assert isinstance(payload["updated_at"], str)
    # ISO-8601 round-trip
    assert datetime.fromisoformat(payload["created_at"])


def test_sensitive_tags_denylist_holds_only_valid_tags() -> None:
    # Starts empty (user decision 2026-07-23: include everything to begin
    # with); anything later added must be a real PersonTag value.
    valid = {tag.value for tag in PersonTag}
    assert SENSITIVE_TAGS <= valid
