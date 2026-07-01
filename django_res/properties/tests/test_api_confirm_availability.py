"""GAP-033 Signal 3 — `POST /properties/{id}:confirm-availability` (staff confirm).

A reservations-writer presses "Mark as up-to-date": the endpoint stamps
`availability_confirmed_at` + `availability_confirmed_by` and adds no dates. It
is gated to the reservations-write floor (a read-only staff viewer is denied)
and never touches the owner-updated signal.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property

pytestmark = pytest.mark.django_db


def test_confirm_availability_stamps_timestamp_and_actor(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:confirm-availability")

    assert response.status_code == 200, response.content
    property_.refresh_from_db()
    assert property_.availability_confirmed_at is not None
    assert property_.availability_confirmed_by_id == staff.pk
    # Confirm adds no dates and does not pose as an owner change.
    assert property_.availability_owner_updated_at is None


def test_confirm_availability_denied_for_non_writer(
    api_client: APIClient, viewer: User, property_: Property
) -> None:
    api_client.force_login(viewer)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:confirm-availability")

    assert response.status_code == 403
    property_.refresh_from_db()
    assert property_.availability_confirmed_at is None
