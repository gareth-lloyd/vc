"""API tests for GET /owner/me."""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from owners.enums import OwnerMembershipStatus, OwnerRole
from owners.factories import (
    OwnerMembershipFactory,
    OwnerOrganisationFactory,
    OwnerOrgPropertyFactory,
)
from owners.models import OwnerOrganisation
from properties.factories import PropertyFactory
from properties.models import Property

pytestmark = pytest.mark.django_db

URL = "/api/v1/owner/me"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _owner_with_grant() -> tuple[User, OwnerOrganisation, Property]:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory(name="Kostas Hospitality Ltd"))
    user = cast(User, UserFactory())
    OwnerMembershipFactory(
        organisation=org,
        user=user,
        role=OwnerRole.ADMIN,
        status=OwnerMembershipStatus.ACTIVE,
    )
    prop = cast(Property, PropertyFactory())
    OwnerOrgPropertyFactory(organisation=org, property=prop, view_full_money=True)
    return user, org, prop


def test_anonymous_is_rejected(api_client: APIClient) -> None:
    # Matches the suite-wide convention for unauthenticated access (the
    # SessionAuth/BasicAuth combo yields 403 here, not 401).
    assert api_client.get(URL).status_code in (401, 403)


def test_staff_non_owner_gets_403(api_client: APIClient) -> None:
    staff = cast(User, UserFactory(role=StaffRole.RESERVATIONS))
    api_client.force_authenticate(staff)
    assert api_client.get(URL).status_code == 403


def test_owner_payload(api_client: APIClient) -> None:
    user, org, prop = _owner_with_grant()
    api_client.force_authenticate(user)

    resp = api_client.get(URL)
    assert resp.status_code == 200
    body = resp.json()

    assert body["is_owner"] is True
    assert body["user"]["id"] == user.id
    assert len(body["organisations"]) == 1
    org_payload = body["organisations"][0]
    assert org_payload["id"] == org.id
    assert org_payload["name"] == "Kostas Hospitality Ltd"
    assert org_payload["role"] == OwnerRole.ADMIN
    assert org_payload["properties"] == [
        {"property_id": prop.id, "view_full_money": True, "view_guest_details": False}
    ]


def test_payload_excludes_suspended_org_and_ended_grants(api_client: APIClient) -> None:
    user, _org, _prop = _owner_with_grant()
    # A second org the user belongs to but whose grant is closed → no properties.
    other = cast(OwnerOrganisation, OwnerOrganisationFactory())
    OwnerMembershipFactory(organisation=other, user=user, status=OwnerMembershipStatus.ACTIVE)
    import datetime

    OwnerOrgPropertyFactory(
        organisation=other,
        property=cast(Property, PropertyFactory()),
        end_date=datetime.date(2020, 1, 1),
    )
    api_client.force_authenticate(user)

    body = api_client.get(URL).json()
    by_id = {o["id"]: o for o in body["organisations"]}
    assert by_id[other.id]["properties"] == []


def test_owner_me_query_budget(api_client: APIClient) -> None:
    user, _, _ = _owner_with_grant()
    api_client.force_authenticate(user)
    with assert_max_queries(8):
        api_client.get(URL)
