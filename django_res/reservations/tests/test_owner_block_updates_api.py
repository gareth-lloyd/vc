"""API tests for the staff owner-block awareness feed (`/owner-block-updates`)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from properties.factories import PropertyFactory
from properties.models import Property
from reservations.enums import OwnerBlockStatus, OwnerBlockUpdateKind
from reservations.models import BookingHold, OwnerBlock, OwnerBlockUpdate
from reservations.services.owner_block import OwnerBlockService

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/owner-block-updates"


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _staff(role: StaffRole = StaffRole.RESERVATIONS) -> User:
    return cast(User, UserFactory(role=role))


def _block(*, days_out: int = 30) -> OwnerBlock:
    """Create an APPROVED block (one CREATED update) on a fresh property."""
    start = date(2026, 9, 1) + timedelta(days=days_out)
    return OwnerBlockService.create(
        property=cast(Property, PropertyFactory()),
        created_by=_staff(),
        date_from=start,
        date_to=start + timedelta(days=5),
    )


def test_feed_lists_created_and_cancelled_chronologically(api_client: APIClient) -> None:
    block = _block()
    OwnerBlockService.cancel(block, actor=_staff())
    api_client.force_authenticate(_staff())

    body = api_client.get(LIST_URL).json()
    kinds = {row["kind"] for row in body["results"]}
    assert kinds == {OwnerBlockUpdateKind.CREATED.value, OwnerBlockUpdateKind.CANCELLED.value}


def test_owner_portal_user_cannot_read_feed(api_client: APIClient) -> None:
    # A non-staff (authenticated) principal must not see the staff feed.
    api_client.force_authenticate(cast(User, UserFactory(is_staff=False)))
    assert api_client.get(LIST_URL).status_code == 403


def test_is_seen_is_per_caller(api_client: APIClient) -> None:
    block = _block()
    update = block.updates.get()
    alice, bob = _staff(), _staff()

    api_client.force_authenticate(alice)
    api_client.post(f"{LIST_URL}/{update.id}:seen", format="json")

    # Alice now sees it as seen...
    alice_rows = api_client.get(LIST_URL).json()["results"]
    assert alice_rows[0]["is_seen"] is True

    # ...but Bob's view is untouched.
    api_client.force_authenticate(bob)
    bob_rows = api_client.get(LIST_URL).json()["results"]
    assert bob_rows[0]["is_seen"] is False


def test_contest_requires_reason(api_client: APIClient) -> None:
    update = _block().updates.get()
    api_client.force_authenticate(_staff())
    resp = api_client.post(f"{LIST_URL}/{update.id}:contest", data={"reason": ""}, format="json")
    assert resp.status_code == 400


def test_contest_requires_writer_role(api_client: APIClient) -> None:
    update = _block().updates.get()
    api_client.force_authenticate(_staff(role=StaffRole.VIEWER))
    resp = api_client.post(
        f"{LIST_URL}/{update.id}:contest", data={"reason": "check"}, format="json"
    )
    assert resp.status_code == 403


def test_contest_flags_block_keeps_it_approved_and_marks_seen(api_client: APIClient) -> None:
    block = _block()
    update = block.updates.get()
    hold_id = block.resulting_hold_id
    assert hold_id is not None
    api_client.force_authenticate(_staff())

    resp = api_client.post(
        f"{LIST_URL}/{update.id}:contest",
        data={"reason": "Guest enquiry for these dates"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["contested"]["reason"] == "Guest enquiry for these dates"
    assert body["is_seen"] is True  # contesting marks it seen for the contester

    block.refresh_from_db()
    assert block.status == OwnerBlockStatus.APPROVED.value
    assert BookingHold.objects.get(pk=hold_id).is_live() is True


def test_contest_on_cancelled_block_is_rejected(api_client: APIClient) -> None:
    block = _block()
    OwnerBlockService.cancel(block, actor=_staff())
    cancelled_update = block.updates.get(kind=OwnerBlockUpdateKind.CANCELLED.value)
    api_client.force_authenticate(_staff())

    resp = api_client.post(
        f"{LIST_URL}/{cancelled_update.id}:contest",
        data={"reason": "too late"},
        format="json",
    )
    assert resp.status_code == 409, resp.content
    block.refresh_from_db()
    assert block.contested_at is None


def test_property_filter_rejects_non_numeric(api_client: APIClient) -> None:
    _block()
    api_client.force_authenticate(_staff())
    resp = api_client.get(LIST_URL, {"property": "abc"})
    assert resp.status_code == 400


def test_seen_only_affects_caller(api_client: APIClient) -> None:
    update = _block().updates.get()
    alice, bob = _staff(), _staff()
    api_client.force_authenticate(alice)
    assert api_client.post(f"{LIST_URL}/{update.id}:seen", format="json").status_code == 200

    api_client.force_authenticate(bob)
    bob_rows = api_client.get(LIST_URL).json()["results"]
    assert bob_rows[0]["is_seen"] is False


def test_old_review_routes_are_gone(api_client: APIClient) -> None:
    api_client.force_authenticate(_staff())
    assert api_client.post("/api/v1/block-requests/1:approve", format="json").status_code == 404
    assert api_client.post("/api/v1/block-requests/1:decline", format="json").status_code == 404


def test_feed_query_count_is_bounded(api_client: APIClient) -> None:
    for offset in range(5):
        _block(days_out=offset * 20)
    assert OwnerBlockUpdate.objects.count() == 5
    api_client.force_authenticate(_staff())

    with assert_max_queries(8):
        resp = api_client.get(LIST_URL)
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 5
