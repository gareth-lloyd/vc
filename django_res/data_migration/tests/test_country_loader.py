from __future__ import annotations

from datetime import datetime

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
def test_deleted_country_loads_inactive_even_when_is_active_set(
    villa_country_row: dict[str, object],
) -> None:
    # GAP-107: legacy soft-delete beats the IsActive flag. The row still
    # loads (villas/regions may point at it) but is retired.
    row = {
        **villa_country_row,
        "IsActive": True,
        "DeletedAt": datetime(2024, 3, 1),
        "DeletedBy": "x",
    }
    loader = CountryLoader()
    loader._process_row(row, LoadReport(loader=loader.name))
    fr = Country.objects.get(iso2="FR")
    assert fr.legacy_id == "42"
    assert fr.is_active is False


@pytest.mark.django_db
def test_live_row_claims_iso2_before_deleted_duplicate(
    villa_country_row: dict[str, object],
) -> None:
    """Two legacy rows share an iso2 (one deleted). Whatever order the cursor
    yields them, the live row must own the ISO seed's legacy_id, and the
    deleted duplicate must not overwrite it."""
    deleted_dup = {
        **villa_country_row,
        "Id": 7,
        "Name": "France (old)",
        "DeletedAt": datetime(2020, 1, 1),
    }
    loader = CountryLoader()
    report = LoadReport(loader=loader.name)
    loader._load_rows([deleted_dup, villa_country_row], report)
    fr = Country.objects.get(iso2="FR")
    assert fr.legacy_id == "42"
    assert fr.is_active is True
    assert fr.name == "France"
    assert report.skipped == 1


@pytest.mark.django_db
def test_live_row_displaces_a_deleted_twins_earlier_claim(
    villa_country_row: dict[str, object],
) -> None:
    """A DB loaded before GAP-107 (or a legacy delete-and-recreate) can
    already carry the deleted twin's legacy_id on the ISO seed. The live row
    must take the seed over, or re-runs never converge and the live legacy
    id resolves nowhere."""
    fr = Country.objects.get(iso2="FR")
    fr.legacy_id = "7"
    fr.is_active = False
    fr.save(update_fields=["legacy_id", "is_active"])
    deleted_dup = {
        **villa_country_row,
        "Id": 7,
        "Name": "France (old)",
        "DeletedAt": datetime(2020, 1, 1),
    }
    loader = CountryLoader()
    report = LoadReport(loader=loader.name)
    loader._load_rows([deleted_dup, villa_country_row], report)
    fr.refresh_from_db()
    assert fr.legacy_id == "42"
    assert fr.is_active is True
    assert fr.name == "France"
    # The deleted twin is skipped, not written over the live row's claim.
    assert report.skipped == 1


@pytest.mark.django_db
def test_live_claim_is_never_displaced_by_a_different_live_row(
    villa_country_row: dict[str, object],
) -> None:
    fr = Country.objects.get(iso2="FR")
    fr.legacy_id = "7"
    fr.save(update_fields=["legacy_id"])
    loader = CountryLoader()
    report = LoadReport(loader=loader.name)
    loader._load_rows([villa_country_row], report)
    fr.refresh_from_db()
    assert fr.legacy_id == "7"
    assert report.skipped == 1


def test_legacy_query_selects_deletion_columns() -> None:
    assert "DeletedAt" in CountryLoader.legacy_query
    assert "DeletedBy" in CountryLoader.legacy_query


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
