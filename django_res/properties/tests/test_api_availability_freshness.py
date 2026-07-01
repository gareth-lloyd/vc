"""GAP-033 — the three freshness signals are serialized on list + detail.

Detail and list both expose: availability_owner_updated_at (Signal 1),
availability_confirmed_at + availability_confirmed_by_name (Signal 3), and
calendar_last_imported_at (Signal 2, derived from the latest active feed poll;
null when the property has no feed).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Property, PropertyCalendarFeed
from properties.services import PropertyAvailabilityService

pytestmark = pytest.mark.django_db

_FRESHNESS_KEYS = {
    "availability_owner_updated_at",
    "availability_confirmed_at",
    "availability_confirmed_by_name",
    "calendar_last_imported_at",
}


def test_detail_serializes_all_freshness_signals(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyAvailabilityService.touch_owner_updated(property_)
    PropertyAvailabilityService.confirm(property_, actor=staff)

    api_client.force_login(staff)
    body = api_client.get(f"/api/v1/properties/{property_.pk}").json()

    assert _FRESHNESS_KEYS <= set(body)
    assert body["availability_owner_updated_at"] is not None
    assert body["availability_confirmed_at"] is not None
    assert body["availability_confirmed_by_name"] == (staff.get_full_name() or staff.email)


def test_calendar_last_imported_at_reflects_active_feed(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    polled = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)
    PropertyCalendarFeed.objects.create(
        property=property_,
        url="https://example.test/ical/feed.ics",
        is_active=True,
        last_polled_at=polled,
    )

    api_client.force_login(staff)
    body = api_client.get(f"/api/v1/properties/{property_.pk}").json()

    assert body["calendar_last_imported_at"] is not None
    assert body["has_active_ical_feed"] is True


def test_calendar_last_imported_at_null_without_feed(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    body = api_client.get(f"/api/v1/properties/{property_.pk}").json()

    assert body["calendar_last_imported_at"] is None
    assert body["has_active_ical_feed"] is False


def test_list_serializes_freshness_signals(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyAvailabilityService.confirm(property_, actor=staff)

    api_client.force_login(staff)
    body = api_client.get("/api/v1/properties").json()

    row = next(r for r in body["results"] if r["id"] == property_.pk)
    assert _FRESHNESS_KEYS <= set(row)
    assert row["availability_confirmed_by_name"] == (staff.get_full_name() or staff.email)
