"""API tests for the operator block-request review queue (`/block-requests`)."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from accounts.models import User
from core.enums import StaffRole
from owners.enums import OwnerMembershipStatus
from owners.factories import OwnerMembershipFactory, OwnerOrganisationFactory
from owners.models import OwnerOrganisation
from properties.models import Property
from reservations.enums import OwnerBlockRequestStatus
from reservations.models import OwnerBlockRequest
from reservations.services.holds import HoldService

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/block-requests"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _owner() -> User:
    """A pure portal owner — not staff, so blocked from the operator queue."""
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = cast(User, UserFactory(is_staff=False))
    OwnerMembershipFactory(organisation=org, user=user, status=OwnerMembershipStatus.ACTIVE)
    return user


def _pending(property_: Property) -> OwnerBlockRequest:
    start = timezone.localdate() + timedelta(days=20)
    return OwnerBlockRequest.objects.create(
        property=property_,
        requested_by=_owner(),
        date_from=start,
        date_to=start + timedelta(days=5),
    )


def test_staff_can_list_queue(api_client: APIClient, property_: Property) -> None:
    _pending(property_)
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.VIEWER)))
    resp = api_client.get(f"{LIST_URL}?status=pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_owner_cannot_reach_operator_queue(api_client: APIClient) -> None:
    api_client.force_authenticate(_owner())
    assert api_client.get(LIST_URL).status_code == 403


def test_viewer_cannot_approve(api_client: APIClient, property_: Property) -> None:
    req = _pending(property_)
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.VIEWER)))
    resp = api_client.post(f"{LIST_URL}/{req.id}:approve", format="json")
    assert resp.status_code == 403


def test_reservations_role_approves_and_places_hold(
    api_client: APIClient, property_: Property
) -> None:
    req = _pending(property_)
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.RESERVATIONS)))

    resp = api_client.post(f"{LIST_URL}/{req.id}:approve", format="json")
    assert resp.status_code == 200, resp.content
    req.refresh_from_db()
    assert req.status == OwnerBlockRequestStatus.APPROVED.value
    assert req.resulting_hold is not None
    assert req.resulting_hold.is_live() is True


def test_decline(api_client: APIClient, property_: Property) -> None:
    req = _pending(property_)
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.RESERVATIONS)))
    resp = api_client.post(
        f"{LIST_URL}/{req.id}:decline",
        data={"review_note": "Dates clash with maintenance window"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    req.refresh_from_db()
    assert req.status == OwnerBlockRequestStatus.DECLINED.value
    assert req.review_note == "Dates clash with maintenance window"


def test_approve_conflict_returns_409(api_client: APIClient, property_: Property) -> None:
    req = _pending(property_)
    # A live hold lands on the same range before approval.
    HoldService.place(
        property=property_,
        date_from=req.date_from,
        date_to=req.date_to,
        never_expires=True,
    )
    api_client.force_authenticate(cast(User, UserFactory(role=StaffRole.RESERVATIONS)))
    resp = api_client.post(f"{LIST_URL}/{req.id}:approve", format="json")
    assert resp.status_code == 409
    req.refresh_from_db()
    assert req.status == OwnerBlockRequestStatus.PENDING.value
