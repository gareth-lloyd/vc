"""`category` filter + pagination on `GET /features` (BUG-019 #3, #4).

`FeatureViewSet` declared no filterset (the Tags admin category picker was a
no-op) and no `pagination_class` (the ~300-row catalogue truncated at the
global `PAGE_SIZE=50`). Both are live bugs — this pins the fix.
"""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from properties.factories import FeatureCategoryFactory, FeatureFactory
from properties.models import FeatureCategory

pytestmark = pytest.mark.django_db


@pytest.fixture
def outdoor(db: None) -> FeatureCategory:
    return cast(FeatureCategory, FeatureCategoryFactory(name="Outdoor", slug="outdoor"))


@pytest.fixture
def kitchen(db: None) -> FeatureCategory:
    return cast(FeatureCategory, FeatureCategoryFactory(name="Kitchen", slug="kitchen"))


def _slugs(body: dict) -> set[str]:
    return {row["slug"] for row in body["results"]}


class TestFeatureCategoryFilter:
    def test_category_slug_filters(
        self, api_client: APIClient, outdoor: FeatureCategory, kitchen: FeatureCategory
    ) -> None:
        pool = FeatureFactory(category=outdoor, slug="pool")
        FeatureFactory(category=kitchen, slug="oven")
        resp = api_client.get("/api/v1/features", {"category": "outdoor"})
        assert resp.status_code == 200
        assert _slugs(resp.json()) == {pool.slug}

    def test_category_id_filters(
        self, api_client: APIClient, outdoor: FeatureCategory, kitchen: FeatureCategory
    ) -> None:
        pool = FeatureFactory(category=outdoor, slug="pool")
        FeatureFactory(category=kitchen, slug="oven")
        resp = api_client.get("/api/v1/features", {"category": str(outdoor.pk)})
        assert resp.status_code == 200
        assert _slugs(resp.json()) == {pool.slug}

    def test_no_category_returns_all(
        self, api_client: APIClient, outdoor: FeatureCategory, kitchen: FeatureCategory
    ) -> None:
        FeatureFactory(category=outdoor, slug="pool")
        FeatureFactory(category=kitchen, slug="oven")
        resp = api_client.get("/api/v1/features")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    def test_unknown_category_slug_returns_empty_not_error(
        self, api_client: APIClient, outdoor: FeatureCategory
    ) -> None:
        FeatureFactory(category=outdoor, slug="pool")
        resp = api_client.get("/api/v1/features", {"category": "does-not-exist"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_unknown_category_id_returns_empty_not_error(
        self, api_client: APIClient, outdoor: FeatureCategory
    ) -> None:
        FeatureFactory(category=outdoor, slug="pool")
        resp = api_client.get("/api/v1/features", {"category": "999999"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestFeaturePagination:
    def test_page_size_param_is_honoured(
        self, api_client: APIClient, outdoor: FeatureCategory
    ) -> None:
        FeatureFactory.create_batch(60, category=outdoor)
        resp = api_client.get("/api/v1/features", {"page_size": "500"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 60
        assert len(resp.json()["results"]) == 60

    def test_default_page_size_still_paginates(
        self, api_client: APIClient, outdoor: FeatureCategory
    ) -> None:
        FeatureFactory.create_batch(60, category=outdoor)
        resp = api_client.get("/api/v1/features")
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 60
        assert len(body["results"]) < 60


class TestFeatureCategoryPagination:
    def test_page_size_param_is_honoured(self, api_client: APIClient) -> None:
        FeatureCategoryFactory.create_batch(60)
        resp = api_client.get("/api/v1/feature-categories", {"page_size": "500"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 60
        assert len(resp.json()["results"]) == 60
