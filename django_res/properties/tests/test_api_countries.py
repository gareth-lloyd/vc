"""API tests for /countries — page-size override.

The country list backs `<Select>` pickers (e.g. the property location form)
that need every row in one request, so it accepts a `page_size` override.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties.models import Country


@pytest.fixture
def many_countries(db: None) -> None:
    # 60 unique 2-char ISO codes: A0..A9, B0..B9, … F0..F9.
    Country.objects.bulk_create(
        Country(
            iso2=f"{chr(65 + i // 10)}{i % 10}",
            iso3=f"{chr(65 + i // 10)}{i % 10}X",
            name=f"Country {i}",
        )
        for i in range(60)
    )


@pytest.mark.django_db
def test_country_list_defaults_to_page_size(
    api_client: APIClient, staff: User, many_countries: None
) -> None:
    api_client.force_login(staff)
    response = api_client.get("/api/v1/countries")
    assert response.status_code == 200, response.content
    # Default page size caps the page at 50 even though 60 exist.
    assert len(response.json()["results"]) == 50


@pytest.mark.django_db
def test_country_list_honours_page_size_override(
    api_client: APIClient, staff: User, many_countries: None
) -> None:
    api_client.force_login(staff)
    response = api_client.get("/api/v1/countries", {"page_size": 500})
    assert response.status_code == 200, response.content
    body = response.json()
    # A large page returns every row in one request (no truncation to 50).
    assert body["count"] >= 60
    assert len(body["results"]) == body["count"]
