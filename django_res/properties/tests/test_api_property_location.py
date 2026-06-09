"""API tests for /properties/{id}/location.

The location endpoint mirrors the settings/finance singleton-subresource shape:
a GET lazily provisions a default `PropertyLocation` (country from the region,
timezone from `representative_timezone`) so location-less properties heal on
first access. PATCH edits address, country, coordinates, and timezone.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.tests import assert_max_queries
from properties.models import Country, Property, PropertyLocation


@pytest.mark.django_db
def test_get_location_provisions_default(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    assert not PropertyLocation.objects.filter(property=property_).exists()
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/location")
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["property"] == property_.pk
    assert body["country"] == property_.region.country_id
    # GB region → Europe/London.
    assert body["timezone"] == "Europe/London"
    assert PropertyLocation.objects.filter(property=property_).exists()


@pytest.mark.django_db
def test_patch_location_updates_fields(
    api_client: APIClient,
    staff: User,
    property_: Property,
    country: Country,
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/location",
        data={
            "address_line_1": "12 Cliff Road",
            "locality_town": "St Ives",
            "post_code": "TR26 1AA",
            "country": country.pk,
            "latitude": "50.211800",
            "longitude": "-5.480700",
            "timezone": "Europe/London",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    location = PropertyLocation.objects.get(property=property_)
    assert location.address_line_1 == "12 Cliff Road"
    assert location.locality_town == "St Ives"
    assert location.post_code == "TR26 1AA"
    assert str(location.latitude) == "50.211800"
    assert str(location.longitude) == "-5.480700"
    assert location.timezone == "Europe/London"


@pytest.mark.django_db
def test_patch_location_rejects_invalid_timezone(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/location",
        data={"timezone": "Mars/Phobos"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "timezone" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_location_rejects_out_of_range_latitude(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/location",
        data={"latitude": "95.000000"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "latitude" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_location_rejects_unknown_country(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/location",
        data={"country": 999999},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "country" in response.json()["field_errors"]


@pytest.mark.django_db
def test_location_requires_reservations_writer(
    api_client: APIClient, viewer: User, property_: Property
) -> None:
    api_client.force_login(viewer)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/location",
        data={"locality_town": "St Ives"},
        format="json",
    )
    assert response.status_code == 403, response.content


@pytest.mark.django_db
def test_get_location_query_count(api_client: APIClient, staff: User, property_: Property) -> None:
    PropertyLocation.objects.create(
        property=property_, country=property_.region.country, timezone="Europe/London"
    )
    api_client.force_login(staff)
    with assert_max_queries(6):
        response = api_client.get(f"/api/v1/properties/{property_.pk}/location")
    assert response.status_code == 200, response.content
