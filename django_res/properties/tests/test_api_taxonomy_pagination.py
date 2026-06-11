"""Regions and collections honour a client `page_size`.

Both lists populate filter `<Select>`s (e.g. the availability timeline
toolbar), which need every row in one request — the default fixed page size
of 50 would silently truncate them as the portfolio grows.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from properties.models import Collection, Country, Region

pytestmark = pytest.mark.django_db


@pytest.fixture
def many_regions(country: Country) -> None:
    Region.objects.bulk_create(
        Region(country=country, name=f"Region {n:03d}", slug=f"region-{n:03d}") for n in range(60)
    )


@pytest.fixture
def many_collections(db: None) -> None:
    Collection.objects.bulk_create(
        Collection(name=f"Collection {n:03d}", slug=f"collection-{n:03d}") for n in range(60)
    )


def test_regions_honour_page_size(api_client: APIClient, many_regions: None) -> None:
    resp = api_client.get("/api/v1/regions", {"page_size": "200"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(body["results"])


def test_collections_honour_page_size(api_client: APIClient, many_collections: None) -> None:
    resp = api_client.get("/api/v1/collections", {"page_size": "200"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(body["results"])
