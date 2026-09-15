"""RegionLoader (GAP-107): legacy-deleted regions, and regions under a
country that is not selectable, load INACTIVE — never skipped.

Transform tests on hand-rolled dict fixtures. `django_db` only where the
country FK resolves against loaded rows.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from data_migration.loaders.lookups import RegionLoader
from data_migration.loaders.sentinels import unknown_country
from properties.models.geo import Country


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "Id": 7,
        "Name": "Cornwall",
        "Slug": "cornwall",
        "CountryId": 42,
        "DeletedAt": None,
        "DeletedBy": None,
    }
    row.update(overrides)
    return row


@pytest.fixture
def france(db: None) -> Country:
    country, _ = Country.objects.get_or_create(
        iso2="FR", defaults={"name": "France", "iso3": "FRA"}
    )
    country.legacy_id = "42"
    country.is_active = True
    country.save(update_fields=["legacy_id", "is_active"])
    return country


def _transform(row: dict[str, Any]) -> dict[str, Any]:
    kwargs = RegionLoader().transform(row)
    assert kwargs is not None
    return kwargs


@pytest.mark.django_db
def test_live_region_under_live_country_is_active(france: Country) -> None:
    kwargs = _transform(_row())
    assert kwargs["is_active"] is True
    assert kwargs["country"] == france
    assert kwargs["name"] == "Cornwall"


@pytest.mark.django_db
def test_deleted_at_marks_region_inactive(france: Country) -> None:
    kwargs = _transform(_row(DeletedAt=datetime(2024, 1, 1)))
    assert kwargs["is_active"] is False
    assert kwargs["country"] == france


@pytest.mark.django_db
def test_deleted_by_alone_marks_region_inactive(france: Country) -> None:
    # Legacy's own views key deletion on `ISNULL(DeletedBy,'') <> ''`; the
    # `sp_*` DELETE paths write both, but honour either.
    kwargs = _transform(_row(DeletedBy="admin"))
    assert kwargs["is_active"] is False


@pytest.mark.django_db
def test_orphan_under_unknown_country_is_inactive_on_sentinel() -> None:
    # No loaded Country carries legacy_id 999 → sentinel (which is inactive).
    kwargs = _transform(_row(CountryId=999))
    assert kwargs["is_active"] is False
    assert kwargs["country"] == unknown_country()


@pytest.mark.django_db
def test_region_under_retired_country_is_inactive_but_still_resolves(france: Country) -> None:
    # CountryLoader retires a deleted (or `IsActive = 0`) country in place;
    # the region's FK still resolves to it, but the region is not selectable.
    france.is_active = False
    france.save(update_fields=["is_active"])
    kwargs = _transform(_row())
    assert kwargs["is_active"] is False
    assert kwargs["country"] == france


def test_blank_name_is_skipped() -> None:
    assert RegionLoader().transform(_row(Name="   ")) is None


@pytest.mark.django_db
def test_name_truncated_to_model_width(france: Country) -> None:
    # Legacy `VillaRegion.Name` is nvarchar(500); `Region.name` is 128.
    kwargs = _transform(_row(Name="x" * 300))
    assert len(kwargs["name"]) == 128


def test_legacy_query_selects_deletion_columns() -> None:
    query = RegionLoader().legacy_query
    assert "DeletedAt" in query
    assert "DeletedBy" in query


# --- BUG-030 §6 / §9 ---


def test_region_under_legacy_england_attaches_to_gb(db: None) -> None:
    kwargs = _transform(_row(CountryId=24))
    assert kwargs["country"] == Country.objects.get(iso2="GB")


def test_region_slug_is_slugified(france: Country) -> None:
    # BUG-030 §9: legacy slugs carry accents (`andalucía`); `Region.slug` is a
    # SlugField, so normalise before suffixing the legacy id.
    kwargs = _transform(_row(Id=10, Slug="andalucía"))
    assert kwargs["slug"] == "andalucia-10"


def test_region_with_non_latin_slug_and_name_falls_back_to_the_id(france: Country) -> None:
    kwargs = _transform(_row(Id=61, Slug="πελοπόννησος", Name="Πελοπόννησος"))
    assert kwargs["slug"] == "region-61"
