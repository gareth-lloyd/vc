from __future__ import annotations

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.country import CountryLoader, _resolve_iso2
from properties.models.geo import Country


def test_resolve_iso2_prefers_raw_when_valid() -> None:
    assert _resolve_iso2("France", "FR") == "FR"


def test_resolve_iso2_falls_back_to_name_lookup() -> None:
    # Legacy row had no iso2 — django-countries should resolve by name.
    assert _resolve_iso2("United Kingdom", "") == "GB"
    assert _resolve_iso2("Greece", "") == "GR"


def test_resolve_iso2_returns_none_for_garbage_names() -> None:
    assert _resolve_iso2("ACF", "") is None
    assert _resolve_iso2("", "") is None


@pytest.mark.django_db
def test_upsert_merges_onto_existing_iso2_row(villa_country_row: dict[str, object]) -> None:
    """The ISO-3166 seed pre-creates the canonical FR row with no legacy_id.
    Running CountryLoader should attach the legacy_id rather than INSERT.
    """
    seeded = Country.objects.get(iso2="FR")
    assert seeded.legacy_id is None

    loader = CountryLoader()
    report = LoadReport(loader=loader.name)
    loader._process_row(villa_country_row, report)

    seeded.refresh_from_db()
    assert seeded.legacy_id == "42"
    assert report.updated == 1 and report.created == 0


@pytest.mark.django_db
def test_legacy_row_without_iso_attaches_to_unknown_sentinel() -> None:
    loader = CountryLoader()
    report = LoadReport(loader=loader.name)
    loader._process_row(
        {
            "Id": 99,
            "Name": "Garbage Country",
            "ShortName1": "",
            "ShortName2": "",
            "Code": None,
            "CountryOrder": 0,
            "IsActive": True,
            "TaxRate": None,
        },
        report,
    )
    sentinel = Country.objects.filter(iso2="XX").get()
    assert sentinel.legacy_id == "99"
