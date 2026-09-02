"""GAP-093 — `Property.category` / `PropertyCategory` are gone.

Country + region is enough (owner call, 2026-07-20). These tests pin the
absence: no endpoint, no filter param, no serializer key, and a create that
needs only name / display_name / slug / region. (The Zoho villa payload's
missing `category` key is pinned recursively in `test_zoho_villa.py`.)
"""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from owners.serializers.property import OwnerPropertySerializer
from properties.factories import PropertyFactory
from properties.filters import PropertyFilter
from properties.models import Property, Region

pytestmark = pytest.mark.django_db


def test_property_categories_endpoint_is_gone(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    assert api_client.get("/api/v1/property-categories").status_code == 404


def test_property_filter_has_no_category_param(api_client: APIClient, staff: User) -> None:
    assert "category" not in PropertyFilter.base_filters
    a = cast(Property, PropertyFactory())
    b = cast(Property, PropertyFactory())
    api_client.force_login(staff)
    # django-filter ignores unknown params — old clients get the full list.
    response = api_client.get("/api/v1/properties", {"category": 1})
    assert response.status_code == 200
    assert {row["id"] for row in response.json()["results"]} == {a.pk, b.pk}


def test_create_property_needs_only_four_fields(
    api_client: APIClient, staff: User, region: Region
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/properties",
        data={
            "name": "Fresh Villa",
            "display_name": "Fresh Villa",
            "slug": "fresh-villa",
            "region": region.pk,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert "category" not in response.json()


def test_read_serializers_emit_no_category(api_client: APIClient, staff: User) -> None:
    prop = cast(Property, PropertyFactory())
    api_client.force_login(staff)
    listed = api_client.get("/api/v1/properties").json()["results"][0]
    detail = api_client.get(f"/api/v1/properties/{prop.pk}").json()
    assert "category" not in listed
    assert "category" not in detail
    assert "category" not in OwnerPropertySerializer(prop).data
