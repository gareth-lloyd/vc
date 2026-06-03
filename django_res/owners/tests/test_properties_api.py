"""API tests for the scoped owner properties endpoint."""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from owners.enums import OwnerMembershipStatus
from owners.factories import (
    OwnerMembershipFactory,
    OwnerOrganisationFactory,
    OwnerOrgPropertyFactory,
)
from owners.models import OwnerOrganisation
from properties.factories import PropertyFactory
from properties.models import Property, PropertyCapacity

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/owner/properties"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _owner_of(org: OwnerOrganisation) -> User:
    user = cast(User, UserFactory())
    OwnerMembershipFactory(organisation=org, user=user, status=OwnerMembershipStatus.ACTIVE)
    return user


def _granted_property(org: OwnerOrganisation) -> Property:
    prop = cast(Property, PropertyFactory())
    OwnerOrgPropertyFactory(organisation=org, property=prop)
    return prop


def test_staff_non_owner_gets_403(api_client: APIClient) -> None:
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.RESERVATIONS)))
    assert api_client.get(LIST_URL).status_code == 403


def test_list_returns_only_scoped_properties(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner_of(org)
    mine = _granted_property(org)
    PropertyFactory()  # someone else's villa

    api_client.force_authenticate(user)
    body = api_client.get(LIST_URL).json()
    ids = [row["id"] for row in body["results"]]
    assert ids == [mine.id]


def test_detail_of_ungranted_property_404s(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner_of(org)
    other = cast(Property, PropertyFactory())

    api_client.force_authenticate(user)
    assert api_client.get(f"{LIST_URL}/{other.id}").status_code == 404


def test_detail_exposes_capacity_and_hero(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner_of(org)
    prop = _granted_property(org)
    PropertyCapacity.objects.update_or_create(property=prop, defaults={"guests": 8, "bedrooms": 4})

    api_client.force_authenticate(user)
    body = api_client.get(f"{LIST_URL}/{prop.id}").json()
    assert body["id"] == prop.id
    assert body["guests"] == 8
    assert body["bedrooms"] == 4
    assert "hero_image_url" in body


def test_list_query_budget(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner_of(org)
    for _ in range(5):
        _granted_property(org)

    api_client.force_authenticate(user)
    with assert_max_queries(10):
        api_client.get(LIST_URL)
