"""`features=` AND filter on `GET /properties` (BUG-019 #1, #2 backend half).

Legacy `FeatureIds` semantics: a property must carry ALL requested features
(AND, not OR). Comma-separated slugs or ids, matching manual and derived
`PropertyFeature` links alike, with a stable `.distinct()` count.
"""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties import factories
from properties.models import Feature, FeatureCategory, Property, PropertyFeature, Region

pytestmark = pytest.mark.django_db


@pytest.fixture
def pool(region: Region) -> Feature:
    category = cast(FeatureCategory, factories.FeatureCategoryFactory())
    return cast(Feature, factories.FeatureFactory(name="Pool", slug="pool", category=category))


@pytest.fixture
def sea_view(pool: Feature) -> Feature:
    return cast(
        Feature, factories.FeatureFactory(name="Sea view", slug="sea-view", category=pool.category)
    )


def _ids(body: dict) -> set[int]:
    return {row["id"] for row in body["results"]}


class TestPropertyFeaturesFilter:
    def test_and_semantics_requires_all_requested_features(
        self,
        api_client: APIClient,
        staff: User,
        region: Region,
        pool: Feature,
        sea_view: Feature,
    ) -> None:
        both = cast(Property, factories.PropertyFactory(region=region))
        both.features.set([pool, sea_view])
        pool_only = cast(Property, factories.PropertyFactory(region=region))
        pool_only.features.set([pool])

        api_client.force_login(staff)
        resp = api_client.get("/api/v1/properties", {"features": f"{pool.slug},{sea_view.slug}"})
        assert resp.status_code == 200
        assert _ids(resp.json()) == {both.pk}

    def test_single_feature_matches_any_property_carrying_it(
        self, api_client: APIClient, staff: User, region: Region, pool: Feature, sea_view: Feature
    ) -> None:
        both = cast(Property, factories.PropertyFactory(region=region))
        both.features.set([pool, sea_view])
        pool_only = cast(Property, factories.PropertyFactory(region=region))
        pool_only.features.set([pool])

        api_client.force_login(staff)
        resp = api_client.get("/api/v1/properties", {"features": pool.slug})
        assert resp.status_code == 200
        assert _ids(resp.json()) == {both.pk, pool_only.pk}

    def test_ids_are_accepted_alongside_slugs(
        self, api_client: APIClient, staff: User, region: Region, pool: Feature
    ) -> None:
        target = cast(Property, factories.PropertyFactory(region=region))
        target.features.set([pool])

        api_client.force_login(staff)
        resp = api_client.get("/api/v1/properties", {"features": str(pool.pk)})
        assert resp.status_code == 200
        assert _ids(resp.json()) == {target.pk}

    def test_derived_links_match_the_same_as_manual(
        self, api_client: APIClient, staff: User, region: Region, pool: Feature
    ) -> None:
        derived_owner = cast(Property, factories.PropertyFactory(region=region))
        PropertyFeature.objects.create(property=derived_owner, feature=pool, is_derived=True)

        api_client.force_login(staff)
        resp = api_client.get("/api/v1/properties", {"features": pool.slug})
        assert resp.status_code == 200
        assert _ids(resp.json()) == {derived_owner.pk}

    def test_distinct_count_not_inflated_by_multiple_matching_features(
        self, api_client: APIClient, staff: User, region: Region, pool: Feature, sea_view: Feature
    ) -> None:
        """A property matching >1 requested feature must appear once, and the
        paginator `count` must reflect that (not the join row count)."""
        both = cast(Property, factories.PropertyFactory(region=region))
        both.features.set([pool, sea_view])

        api_client.force_login(staff)
        resp = api_client.get("/api/v1/properties", {"features": f"{pool.slug},{sea_view.slug}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 1
        assert [row["id"] for row in body["results"]] == [both.pk]

    def test_no_features_param_returns_all(
        self, api_client: APIClient, staff: User, region: Region, pool: Feature
    ) -> None:
        target = cast(Property, factories.PropertyFactory(region=region))
        target.features.set([pool])
        untagged = cast(Property, factories.PropertyFactory(region=region))

        api_client.force_login(staff)
        resp = api_client.get("/api/v1/properties")
        assert resp.status_code == 200
        assert _ids(resp.json()) == {target.pk, untagged.pk}
