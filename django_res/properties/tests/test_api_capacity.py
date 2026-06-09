"""API tests for /properties/{id}/capacity.

Capacity is a singleton-per-property row (`PropertyCapacity`) edited through a
`RetrieveUpdateAPIView`, mirroring the settings/finance endpoints. The list
endpoint also surfaces a read-only, nullable `capacity` block so the quote
builder can explain why a capacity-less property is hidden from search.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import (
    Property,
    PropertyCapacity,
    PropertyCategory,
    PropertyGroup,
    Region,
)


@pytest.mark.django_db
def test_get_capacity_creates_row_when_missing(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    assert not PropertyCapacity.objects.filter(property=property_).exists()
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/capacity")
    assert response.status_code == 200, response.content
    assert PropertyCapacity.objects.filter(property=property_).exists()
    payload = response.json()
    assert payload["guests"] == 0
    assert payload["bedrooms"] == 0
    assert payload["size_sqm"] is None


@pytest.mark.django_db
def test_patch_capacity_updates_fields(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyCapacity.objects.create(property=property_)
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/capacity",
        data={
            "guests": 8,
            "additional_guests": 2,
            "bedrooms": 4,
            "ensuites": 3,
            "bathrooms": 5,
            "size_sqm": "240.50",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    capacity = PropertyCapacity.objects.get(property=property_)
    assert capacity.guests == 8
    assert capacity.additional_guests == 2
    assert capacity.bedrooms == 4
    assert capacity.ensuites == 3
    assert capacity.bathrooms == 5
    assert str(capacity.size_sqm) == "240.50"


@pytest.mark.django_db
def test_patch_capacity_rejects_negative_guests(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyCapacity.objects.create(property=property_, guests=8)
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/capacity",
        data={"guests": -1},
        format="json",
    )
    assert response.status_code == 400, response.content
    property_.capacity.refresh_from_db()
    assert property_.capacity.guests == 8


@pytest.mark.django_db
def test_patch_capacity_property_field_is_read_only(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyCapacity.objects.create(property=property_, guests=8)
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/capacity",
        data={"guests": 6, "property": 999999},
        format="json",
    )
    assert response.status_code == 200, response.content
    capacity = PropertyCapacity.objects.get(property=property_)
    assert capacity.guests == 6
    assert capacity.property_id == property_.pk


@pytest.mark.django_db
def test_capacity_requires_writer_role(
    api_client: APIClient, viewer: User, property_: Property
) -> None:
    api_client.force_login(viewer)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/capacity",
        data={"guests": 6},
        format="json",
    )
    assert response.status_code == 403, response.content


@pytest.mark.django_db
def test_list_serializer_exposes_capacity_block(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyCapacity.objects.create(property=property_, guests=8, bedrooms=4)
    api_client.force_login(staff)
    response = api_client.get("/api/v1/properties")
    assert response.status_code == 200, response.content
    row = next(r for r in response.json()["results"] if r["id"] == property_.pk)
    assert row["capacity"] == {
        "guests": 8,
        "additional_guests": 0,
        "bedrooms": 4,
        "ensuites": 0,
        "bathrooms": 0,
        "size_sqm": None,
    }


@pytest.mark.django_db
def test_list_serializer_capacity_null_when_missing(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.get("/api/v1/properties")
    assert response.status_code == 200, response.content
    row = next(r for r in response.json()["results"] if r["id"] == property_.pk)
    assert row["capacity"] is None


@pytest.mark.django_db
def test_min_guests_filter_excludes_zero_and_missing_capacity(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    group: PropertyGroup,
    region: Region,
) -> None:
    """Regression: `min_guests` keeps excluding properties whose capacity is
    zero or absent — the list capacity read-field must not change which rows
    are returned."""
    quotable = Property.objects.create(
        name="Big Villa",
        display_name="Big Villa",
        slug="big-villa",
        category=category,
        group=group,
        region=region,
    )
    PropertyCapacity.objects.create(property=quotable, guests=8)
    zero = Property.objects.create(
        name="Zero Villa",
        display_name="Zero Villa",
        slug="zero-villa",
        category=category,
        group=group,
        region=region,
    )
    PropertyCapacity.objects.create(property=zero, guests=0)
    Property.objects.create(
        name="No Capacity Villa",
        display_name="No Capacity Villa",
        slug="no-capacity-villa",
        category=category,
        group=group,
        region=region,
    )
    api_client.force_login(staff)
    response = api_client.get("/api/v1/properties?min_guests=2")
    assert response.status_code == 200, response.content
    slugs = {r["slug"] for r in response.json()["results"]}
    assert "big-villa" in slugs
    assert "zero-villa" not in slugs
    assert "no-capacity-villa" not in slugs
