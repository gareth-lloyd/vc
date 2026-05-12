"""API tests for the availability surface."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property
from reservations.enums import BookingHoldReason
from reservations.models.booking import BookingHold


@pytest.mark.django_db
def test_calendar_get_requires_from_and_to(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/availability")
    assert response.status_code == 400


@pytest.mark.django_db
def test_calendar_get_returns_cells(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.get(
        f"/api/v1/properties/{property_.pk}/availability?from=2026-06-01&to=2026-06-03"
    )
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["property_id"] == property_.pk
    assert len(payload["cells"]) == 3


@pytest.mark.django_db
def test_post_creates_manual_hold(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/availability",
        data={
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "reason": BookingHoldReason.OWNER_BLOCK.value,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert BookingHold.objects.filter(property=property_).count() == 1


@pytest.mark.django_db
def test_extend_hold_action(api_client: APIClient, staff: User, property_: Property) -> None:
    hold = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 7),
        expires_at=timezone.now() + timedelta(days=1),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    new_expiry = timezone.now() + timedelta(days=60)
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/availability/{hold.pk}:extend-hold",
        data={"expires_at": new_expiry.isoformat()},
        format="json",
    )
    assert response.status_code == 200, response.content
    hold.refresh_from_db()
    assert abs((hold.expires_at - new_expiry).total_seconds()) < 5


@pytest.mark.django_db
def test_release_hold_action(api_client: APIClient, staff: User, property_: Property) -> None:
    hold = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 7),
        expires_at=timezone.now() + timedelta(days=10),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/availability/{hold.pk}:release-hold")
    assert response.status_code == 200
    hold.refresh_from_db()
    assert hold.released_at is not None


@pytest.mark.django_db
def test_availability_search(api_client: APIClient, staff: User, property_: Property) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/availability:search",
        data={
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 2,
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    results = response.json()["results"]
    assert any(r["property_id"] == property_.pk for r in results)
