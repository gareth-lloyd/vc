from __future__ import annotations

from datetime import datetime

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.country import CountryLoader, _resolve_iso2
from data_migration.loaders.sentinels import UNKNOWN_LEGACY_ID
from properties.models.geo import Country


def test_resolve_iso2_prefers_raw_when_valid() -> None:
    assert _resolve_iso2("France", "FR") == "FR"


def test_resolve_iso2_falls_back_to_name_lookup() -> None:
    # Legacy row had no iso2 — django-countries should resolve by name.
    assert _resolve_iso2("United Kingdom", "") == "GB"
    assert _resolve_iso2("Greece", "") == "GR"


def test_resolve_iso2_maps_uk_to_gb() -> None:
    # BUG-030 §6: legacy "England" carries `UK`, which is not ISO-3166.
    assert _resolve_iso2("England", "UK") == "GB"


def test_resolve_iso2_rejects_an_unknown_two_letter_code() -> None:
    # BUG-030 §6: any two letters used to be accepted verbatim (minting
    # `Country(iso2="UK")`); now the code must be a real ISO-3166 code,
    # otherwise the name decides.
    assert _resolve_iso2("Greece", "XX") == "GR"
    assert _resolve_iso2("Dev Country", "DC") is None


def test_resolve_iso2_normalises_alpha3_and_numeric_codes() -> None:
    # `Country.iso2` is varchar(2): a swapped-column "GRC" or a numeric code
    # must land on the alpha-2 seed row, never be written verbatim.
    assert _resolve_iso2("Greece", "GRC") == "GR"
    assert _resolve_iso2("", "826") == "GB"


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
    # BUG-029 §3: the sentinel keeps its stable legacy_id — junk rows used to
    # overwrite it "last unknown wins", an order-dependent outcome.
    sentinel = Country.objects.filter(iso2="XX").get()
    assert sentinel.legacy_id == UNKNOWN_LEGACY_ID
    assert report.skipped == 1 and report.updated == 0


@pytest.mark.django_db
def test_legacy_code_is_not_a_dial_code(villa_country_row: dict[str, object]) -> None:
    # BUG-030 §5: `VillaCountry.Code` is an ordering/lookup integer (Greece is
    # 300), not a calling code — the loader must leave `dial_code` alone.
    seeded = Country.objects.get(iso2="FR")
    seeded.dial_code = "+33"
    seeded.save(update_fields=["dial_code"])
    loader = CountryLoader()
    loader._process_row({**villa_country_row, "Code": 300}, LoadReport(loader=loader.name))
    assert Country.objects.get(iso2="FR").dial_code == "+33"
    select_list = CountryLoader.legacy_query.split("FROM")[0].removeprefix("SELECT")
    assert "Code" not in [column.strip() for column in select_list.split(",")]


@pytest.mark.django_db
def test_england_row_never_mints_a_uk_country(villa_country_row: dict[str, object]) -> None:
    # BUG-030 §6: legacy 6 (United Kingdom, no iso, deleted) and 24 (England,
    # `UK`, deleted) both resolve to GB; 6 claims the seed first (Id order)
    # and 24 is skipped — `country_for_legacy_id` aliases it (see test_util).
    loader = CountryLoader()
    report = LoadReport(loader=loader.name)
    base = {
        **villa_country_row,
        "ShortName1": "",
        "ShortName2": "",
        "DeletedAt": datetime(2020, 1, 1),
    }
    rows = [
        {**base, "Id": 6, "Name": "United Kingdom"},
        {**base, "Id": 24, "Name": "England", "ShortName1": "UK"},
    ]
    loader._load_rows(rows, report)
    assert not Country.objects.filter(iso2="UK").exists()
    assert Country.objects.get(iso2="GB").legacy_id == "6"
    assert report.skipped == 1
