"""`has_properties` filter on the country/region lookup lists.

The quote-builder criteria dropdowns must offer only geo values that can
actually match a property — the full ISO-3166 seed (~249 countries) would be
almost entirely dead options. `has_properties=true` narrows each list to rows
with at least one property; without the param the full lookup list is
unchanged.
"""

from __future__ import annotations

from typing import cast

import pytest
from rest_framework.test import APIClient

from properties.factories import PropertyFactory, RegionFactory
from properties.models import Country, Region

pytestmark = pytest.mark.django_db


@pytest.fixture
def in_use_region(country: Country) -> Region:
    region = cast(Region, RegionFactory(country=country, name="Cornwall"))
    PropertyFactory(region=region)
    return region


@pytest.fixture
def unused_region(country: Country) -> Region:
    return cast(Region, RegionFactory(country=country, name="Shetland"))


def _iso2s(body: dict) -> set[str]:
    return {row["iso2"] for row in body["results"]}


def _region_ids(body: dict) -> list[int]:
    return [row["id"] for row in body["results"]]


class TestCountriesHasProperties:
    def test_filters_to_countries_with_properties(
        self, api_client: APIClient, in_use_region: Region
    ) -> None:
        resp = api_client.get("/api/v1/countries", {"has_properties": "true", "page_size": "300"})
        assert resp.status_code == 200
        assert _iso2s(resp.json()) == {in_use_region.country.iso2}

    def test_no_param_returns_full_seeded_list(
        self, api_client: APIClient, in_use_region: Region
    ) -> None:
        resp = api_client.get("/api/v1/countries", {"page_size": "300"})
        assert resp.status_code == 200
        body = resp.json()
        # The ISO-3166 seed migration guarantees far more than the in-use set.
        assert body["count"] > 100

    def test_false_is_a_no_op(self, api_client: APIClient, in_use_region: Region) -> None:
        resp = api_client.get("/api/v1/countries", {"has_properties": "false", "page_size": "300"})
        assert resp.status_code == 200
        assert resp.json()["count"] > 100

    def test_no_duplicate_rows_for_many_properties(
        self, api_client: APIClient, in_use_region: Region, country: Country
    ) -> None:
        PropertyFactory(region=in_use_region)
        PropertyFactory(region=RegionFactory(country=country, name="Devon"))
        resp = api_client.get("/api/v1/countries", {"has_properties": "true", "page_size": "300"})
        assert resp.status_code == 200
        assert [row["iso2"] for row in resp.json()["results"]] == [country.iso2]


class TestRegionsHasProperties:
    def test_filters_to_regions_with_properties(
        self, api_client: APIClient, in_use_region: Region, unused_region: Region
    ) -> None:
        resp = api_client.get("/api/v1/regions", {"has_properties": "true", "page_size": "300"})
        assert resp.status_code == 200
        assert _region_ids(resp.json()) == [in_use_region.pk]

    def test_no_param_returns_all_regions(
        self, api_client: APIClient, in_use_region: Region, unused_region: Region
    ) -> None:
        resp = api_client.get("/api/v1/regions", {"page_size": "300"})
        assert resp.status_code == 200
        assert set(_region_ids(resp.json())) == {in_use_region.pk, unused_region.pk}

    def test_no_duplicate_rows_for_many_properties(
        self, api_client: APIClient, in_use_region: Region
    ) -> None:
        PropertyFactory(region=in_use_region)
        resp = api_client.get("/api/v1/regions", {"has_properties": "true", "page_size": "300"})
        assert resp.status_code == 200
        assert _region_ids(resp.json()) == [in_use_region.pk]

    def test_country_id_scopes_regions(self, api_client: APIClient, country: Country) -> None:
        other = Country.objects.exclude(pk=country.pk).first()
        assert other is not None
        mine = cast(Region, RegionFactory(country=country, name="Algarve"))
        RegionFactory(country=other, name="Provence")
        resp = api_client.get("/api/v1/regions", {"country": str(country.pk), "page_size": "300"})
        assert resp.status_code == 200
        assert _region_ids(resp.json()) == [mine.pk]

    def test_country_iso2_scopes_regions_case_insensitively(
        self, api_client: APIClient, country: Country
    ) -> None:
        other = Country.objects.exclude(pk=country.pk).first()
        assert other is not None
        mine = cast(Region, RegionFactory(country=country, name="Algarve"))
        RegionFactory(country=other, name="Provence")
        resp = api_client.get(
            "/api/v1/regions", {"country_iso2": country.iso2.lower(), "page_size": "300"}
        )
        assert resp.status_code == 200
        assert _region_ids(resp.json()) == [mine.pk]

    def test_unknown_country_id_returns_empty_not_400(
        self, api_client: APIClient, in_use_region: Region
    ) -> None:
        """Stale ids happen (countries hard-delete under merge_country); a
        picker fed a dead bookmark should see an empty list, not an error."""
        resp = api_client.get("/api/v1/regions", {"country": "999999", "page_size": "300"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_country_composes_with_has_properties(
        self, api_client: APIClient, in_use_region: Region, country: Country
    ) -> None:
        RegionFactory(country=country, name="Shetland")  # unused, same country
        resp = api_client.get(
            "/api/v1/regions",
            {"country": str(country.pk), "has_properties": "true", "page_size": "300"},
        )
        assert resp.status_code == 200
        assert _region_ids(resp.json()) == [in_use_region.pk]

    def test_ordering_param_still_honoured(self, api_client: APIClient, country: Country) -> None:
        """Regression guard: adding the filterset must not displace the
        globally-configured OrderingFilter (the frontend sends
        `ordering=name`)."""
        zebra = cast(Region, RegionFactory(country=country, name="Zebra Coast"))
        alpha = cast(Region, RegionFactory(country=country, name="Alpha Bay"))
        PropertyFactory(region=zebra)
        PropertyFactory(region=alpha)
        resp = api_client.get(
            "/api/v1/regions",
            {"has_properties": "true", "ordering": "name", "page_size": "300"},
        )
        assert resp.status_code == 200
        assert _region_ids(resp.json()) == [alpha.pk, zebra.pk]
