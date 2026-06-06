"""API tests for the owner block-request endpoints (`/owner/block-requests`)."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from django.utils import timezone
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
from reservations.enums import OwnerBlockKind, OwnerBlockStatus
from reservations.models import OwnerBlock

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/owner/block-requests"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _owner(org: OwnerOrganisation, role: OwnerRole = OwnerRole.ADMIN) -> User:
    user = cast(User, UserFactory())
    OwnerMembershipFactory(
        organisation=org, user=user, role=role, status=OwnerMembershipStatus.ACTIVE
    )
    return user


def _granted_property(org: OwnerOrganisation) -> Property:
    prop = cast(Property, PropertyFactory())
    OwnerOrgPropertyFactory(organisation=org, property=prop)
    return prop


def _payload(prop: Property) -> dict[str, object]:
    start = timezone.localdate() + timedelta(days=20)
    return {
        "property": prop.id,
        "date_from": start.isoformat(),
        "date_to": (start + timedelta(days=5)).isoformat(),
        "kind": OwnerBlockKind.OWNER_STAY.value,
        "notes": "Family week",
    }


def test_create_block_request(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    prop = _granted_property(org)
    api_client.force_authenticate(user)

    resp = api_client.post(LIST_URL, data=_payload(prop), format="json")
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["status"] == OwnerBlockStatus.PENDING.value
    assert "resulting_hold" not in body
    assert OwnerBlock.objects.filter(created_by=user, property=prop).count() == 1


def test_staff_non_owner_gets_403(api_client: APIClient) -> None:
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.RESERVATIONS)))
    assert api_client.get(LIST_URL).status_code == 403


def test_view_only_member_cannot_create(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org, role=OwnerRole.VIEW_ONLY)
    prop = _granted_property(org)
    api_client.force_authenticate(user)

    resp = api_client.post(LIST_URL, data=_payload(prop), format="json")
    assert resp.status_code == 403


def test_editor_can_create(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org, role=OwnerRole.EDITOR)
    prop = _granted_property(org)
    api_client.force_authenticate(user)

    resp = api_client.post(LIST_URL, data=_payload(prop), format="json")
    assert resp.status_code == 201, resp.content


def test_ungranted_property_404s(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    other = cast(Property, PropertyFactory())
    api_client.force_authenticate(user)

    resp = api_client.post(LIST_URL, data=_payload(other), format="json")
    assert resp.status_code == 404


def test_inverted_date_range_400s(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    prop = _granted_property(org)
    api_client.force_authenticate(user)

    payload = _payload(prop)
    payload["date_to"] = payload["date_from"]
    resp = api_client.post(LIST_URL, data=payload, format="json")
    assert resp.status_code == 400
    assert "date_to" in resp.json()["field_errors"]


def test_list_returns_own_requests_only(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    other_user = _owner(org)
    prop = _granted_property(org)
    api_client.force_authenticate(user)
    api_client.post(LIST_URL, data=_payload(prop), format="json")
    # Another member's request must not show in this caller's list.
    OwnerBlock.objects.create(
        property=prop,
        created_by=other_user,
        date_from=timezone.localdate() + timedelta(days=40),
        date_to=timezone.localdate() + timedelta(days=45),
    )

    body = api_client.get(LIST_URL).json()
    assert len(body) == 1
    assert body[0]["property"] == prop.id


def test_cancel_own_request(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    prop = _granted_property(org)
    api_client.force_authenticate(user)
    created = api_client.post(LIST_URL, data=_payload(prop), format="json").json()

    resp = api_client.post(f"{LIST_URL}/{created['id']}:cancel", format="json")
    assert resp.status_code == 200
    assert resp.json()["status"] == OwnerBlockStatus.CANCELLED.value


def test_cannot_cancel_other_members_request(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    other_user = _owner(org)
    prop = _granted_property(org)
    req = OwnerBlock.objects.create(
        property=prop,
        created_by=other_user,
        date_from=timezone.localdate() + timedelta(days=40),
        date_to=timezone.localdate() + timedelta(days=45),
    )
    api_client.force_authenticate(user)

    resp = api_client.post(f"{LIST_URL}/{req.id}:cancel", format="json")
    assert resp.status_code == 404


def test_list_query_count_bounded(api_client: APIClient) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    prop = _granted_property(org)
    for offset in range(5):
        OwnerBlock.objects.create(
            property=prop,
            created_by=user,
            date_from=timezone.localdate() + timedelta(days=50 + offset * 10),
            date_to=timezone.localdate() + timedelta(days=53 + offset * 10),
        )
    api_client.force_authenticate(user)

    with assert_max_queries(6):
        resp = api_client.get(LIST_URL)
    assert resp.status_code == 200
    assert len(resp.json()) == 5
