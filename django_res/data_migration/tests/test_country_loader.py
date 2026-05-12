from __future__ import annotations

from decimal import Decimal

import pytest

from data_migration.loaders.country import CountryLoader
from properties.models.geo import Country


def test_transform_maps_legacy_fields(villa_country_row: dict[str, object]) -> None:
    kwargs = CountryLoader().transform(villa_country_row)
    assert kwargs == {
        "name": "France",
        "iso2": "FR",
        "iso3": "FRA",
        "dial_code": "+33",
        "default_tax_rate": "20.00",
        "sort_order": 5,
        "is_active": True,
    }


def test_transform_skips_rows_without_iso_codes(
    villa_country_row: dict[str, object],
) -> None:
    villa_country_row["ShortName1"] = None
    assert CountryLoader().transform(villa_country_row) is None


def test_transform_handles_null_optional_fields() -> None:
    row: dict[str, object] = {
        "Id": 7,
        "Name": "  Spain  ",
        "ShortName1": "ES",
        "ShortName2": "ESP",
        "Code": None,
        "CountryOrder": None,
        "IsActive": None,
        "TaxRate": None,
    }
    kwargs = CountryLoader().transform(row)
    assert kwargs is not None
    assert kwargs["name"] == "Spain"
    assert kwargs["dial_code"] == ""
    assert kwargs["default_tax_rate"] == Decimal("0")
    assert kwargs["sort_order"] == 0
    assert kwargs["is_active"] is False


@pytest.mark.django_db
def test_upsert_creates_then_updates(villa_country_row: dict[str, object]) -> None:
    """End-to-end: drive the loader's row processor with a fixture row and
    confirm it creates on first call, updates on second."""
    from data_migration.base import LoadReport

    loader = CountryLoader()
    report = LoadReport(loader=loader.name)

    loader._process_row(villa_country_row, report)
    assert report.created == 1 and report.updated == 0
    assert Country.objects.get(legacy_id="42").iso2 == "FR"

    villa_country_row["Name"] = "France (renamed)"
    loader._process_row(villa_country_row, report)
    assert report.created == 1 and report.updated == 1
    assert Country.objects.get(legacy_id="42").name == "France (renamed)"
