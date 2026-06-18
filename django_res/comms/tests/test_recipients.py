"""Unit tests for `comms.recipients`.

These helpers gate every lifecycle-email handler. Lifecycle round-trip
tests exercise the happy path; this file pins each branch explicitly
so a regression in recipient resolution surfaces as a unit failure,
not a missing email log buried under a signal handler.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from accounts.enums import ContactRole
from accounts.models import Person, User
from accounts.models.person import PersonEmail
from comms.recipients import agent_user_for, guest_email, primary_owner_email
from properties.models import (
    Country,
    Property,
    PropertyCategory,
    PropertyContactAssignment,
    PropertyGroup,
    Region,
)
from reservations.models import Guest


def _build_property(slug_suffix: str) -> Property:
    """Build a minimal property graph for owner-resolution tests."""
    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    region, _ = Region.objects.get_or_create(
        slug=f"sw-{slug_suffix}",
        defaults={"country": country, "name": "South West"},
    )
    category, _ = PropertyCategory.objects.get_or_create(
        slug="villa",
        defaults={"name": "Villa"},
    )
    group = PropertyGroup.objects.create(name=f"Group {slug_suffix}")
    return Property.objects.create(
        name=f"Villa {slug_suffix}",
        display_name=f"Villa {slug_suffix}",
        slug=f"villa-{slug_suffix}",
        category=category,
        group=group,
        region=region,
    )


# ---------------------------------------------------------------------------
# guest_email
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_guest_email_returns_email_when_present() -> None:
    guest = Guest.objects.create(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )

    assert guest_email(guest) == "ada@example.com"


def test_guest_email_returns_none_for_none_guest() -> None:
    assert guest_email(None) is None


@pytest.mark.django_db
def test_guest_email_returns_none_for_empty_string() -> None:
    # A phone-only guest is the real "no email" state: email="" normalizes to
    # NULL on save, and the phone keeps the ACTIVE row contactable.
    guest = Guest.objects.create(
        first_name="Ada",
        last_name="Lovelace",
        email="",
        phone="+447911123456",
    )

    assert guest_email(guest) is None


# ---------------------------------------------------------------------------
# primary_owner_email
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_primary_owner_email_returns_primary_contact_primary_email() -> None:
    property_ = _build_property("primary")
    contact = Person.objects.create(first_name="Olive", last_name="Owner")
    PersonEmail.objects.create(contact=contact, email="secondary@example.com", is_primary=False)
    PersonEmail.objects.create(contact=contact, email="primary@example.com", is_primary=True)
    PropertyContactAssignment.objects.create(
        property=property_,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=True,
    )

    assert primary_owner_email(property_) == "primary@example.com"


@pytest.mark.django_db
def test_primary_owner_email_falls_back_to_oldest_email_when_no_primary() -> None:
    """With no `is_primary=True` row, the helper returns the oldest by pk.

    Two non-primary rows are created so the assertion pins the fallback's
    ordering contract — not just `.first()` happening to return the only row.
    """
    property_ = _build_property("fallback")
    contact = Person.objects.create(first_name="Olive", last_name="Owner")
    older = PersonEmail.objects.create(contact=contact, email="older@example.com", is_primary=False)
    PersonEmail.objects.create(contact=contact, email="newer@example.com", is_primary=False)
    PropertyContactAssignment.objects.create(
        property=property_,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=True,
    )

    assert primary_owner_email(property_) == older.email


@pytest.mark.django_db
def test_primary_owner_email_returns_email_for_future_end_date() -> None:
    """A scheduled-to-end-later assignment is still active today."""
    property_ = _build_property("future-end")
    contact = Person.objects.create(first_name="Olive", last_name="Owner")
    PersonEmail.objects.create(contact=contact, email="future-owner@example.com", is_primary=True)
    PropertyContactAssignment.objects.create(
        property=property_,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=True,
        end_date=date.today() + timedelta(days=30),
    )

    assert primary_owner_email(property_) == "future-owner@example.com"


@pytest.mark.django_db
def test_primary_owner_email_returns_none_for_ended_assignment() -> None:
    property_ = _build_property("ended")
    contact = Person.objects.create(first_name="Olive", last_name="Owner")
    PersonEmail.objects.create(contact=contact, email="ex-owner@example.com", is_primary=True)
    PropertyContactAssignment.objects.create(
        property=property_,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=True,
        end_date=date.today(),
    )

    assert primary_owner_email(property_) is None


@pytest.mark.django_db
def test_primary_owner_email_returns_none_for_non_primary_assignment() -> None:
    property_ = _build_property("nonprimary")
    contact = Person.objects.create(first_name="Olive", last_name="Owner")
    PersonEmail.objects.create(
        contact=contact, email="secondary-owner@example.com", is_primary=True
    )
    PropertyContactAssignment.objects.create(
        property=property_,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=False,
    )

    assert primary_owner_email(property_) is None


@pytest.mark.django_db
def test_primary_owner_email_returns_none_when_contact_has_no_email() -> None:
    property_ = _build_property("noemail")
    contact = Person.objects.create(first_name="Olive", last_name="Owner")
    PropertyContactAssignment.objects.create(
        property=property_,
        contact=contact,
        role=ContactRole.OWNER,
        is_primary=True,
    )

    assert primary_owner_email(property_) is None


# ---------------------------------------------------------------------------
# agent_user_for
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_agent_user_for_returns_user() -> None:
    user = User.objects.create_user(email="agnes@example.com", password="pw")
    agent = Person.objects.create(first_name="Agnes", last_name="Agent", user=user)

    class StubQuotation:
        pass

    quotation = StubQuotation()
    quotation.agent = agent  # type: ignore[attr-defined]

    assert agent_user_for(quotation) == user  # type: ignore[arg-type]


def test_agent_user_for_returns_none_without_agent() -> None:
    class StubQuotation:
        agent = None

    assert agent_user_for(StubQuotation()) is None  # type: ignore[arg-type]


@pytest.mark.django_db
def test_agent_user_for_returns_none_when_contact_lacks_user() -> None:
    agent = Person.objects.create(first_name="Boris", last_name="Agent")

    class StubQuotation:
        pass

    quotation = StubQuotation()
    quotation.agent = agent  # type: ignore[attr-defined]

    assert agent_user_for(quotation) is None  # type: ignore[arg-type]
