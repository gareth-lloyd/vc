"""API tests for /properties/{id}/settings — timezone surfacing (FG-008).

Timezone physically lives on `PropertyLocation` (a geographic fact of the
place) but is surfaced through the settings endpoint so ops edit it beside the
check-in/out times it contextualises.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.tests import assert_max_queries
from properties.models import Country, Property, PropertyLocation


@pytest.fixture
def location(property_: Property, country: Country) -> PropertyLocation:
    return PropertyLocation.objects.create(
        property=property_,
        country=country,
        timezone="Europe/London",
    )


@pytest.mark.django_db
def test_get_settings_returns_location_timezone(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["timezone"] == "Europe/London"


@pytest.mark.django_db
def test_get_settings_timezone_null_when_no_location(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["timezone"] is None


@pytest.mark.django_db
def test_patch_settings_updates_timezone(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"timezone": "Europe/Rome"},
        format="json",
    )
    assert response.status_code == 200, response.content
    location.refresh_from_db()
    assert location.timezone == "Europe/Rome"


@pytest.mark.django_db
def test_get_settings_query_count_pins_location_join(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
) -> None:
    """The settings GET joins `property.location` up front, so reading the
    timezone adds no per-request SELECT. Pin the count so a dropped
    `select_related` (the N+1 regression) is caught."""
    api_client.force_login(staff)
    # Warm the request once so the `get_or_create` of PropertySettings is an
    # existing-row SELECT (not an INSERT) on the measured call.
    api_client.get(f"/api/v1/properties/{property_.pk}/settings")

    with assert_max_queries(6):
        response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["timezone"] == "Europe/London"


@pytest.mark.django_db
def test_patch_settings_rejects_invalid_timezone(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"timezone": "Mars/Phobos"},
        format="json",
    )
    assert response.status_code == 400, response.content
    location.refresh_from_db()
    assert location.timezone == "Europe/London"


@pytest.mark.django_db
def test_patch_settings_other_field_leaves_timezone(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"check_in_time": "16:00"},
        format="json",
    )
    assert response.status_code == 200, response.content
    location.refresh_from_db()
    assert location.timezone == "Europe/London"


@pytest.mark.django_db
def test_patch_timezone_without_location_is_rejected(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"timezone": "Europe/Rome"},
        format="json",
    )
    assert response.status_code == 400, response.content
