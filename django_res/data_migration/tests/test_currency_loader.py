"""BUG-028: CurrencyLoader — the live EUR row wins; deleted rows retire.

Legacy `VillaCurrency` carries two EUR rows: Id 2 (soft-deleted 2023) and
Id 3 (live, `IsDefault = 1`, referenced by settings, rate rows, quotations
and bookings). Keep-first stamped the deleted Id 2, so every CurrencyId 3
reference resolved nowhere. Same retire-not-skip rules as CountryLoader
(GAP-107).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.lookups import CurrencyLoader
from pricing.models.currency import Currency

LIVE_EUR: dict[str, Any] = {"Id": 3, "Name": "Euro", "Code": "EUR", "Symbol": "€"}
DELETED_EUR: dict[str, Any] = {
    "Id": 2,
    "Name": "Euro (old)",
    "Code": "EUR",
    "Symbol": "€",
    "DeletedAt": datetime(2023, 10, 21),
    "DeletedBy": "admin",
}


def _load(rows: list[dict[str, Any]]) -> LoadReport:
    loader = CurrencyLoader()
    report = LoadReport(loader=loader.name)
    loader._load_rows(rows, report)
    return report


@pytest.mark.django_db
def test_deleted_row_loads_retired_with_its_legacy_id() -> None:
    _load([{**DELETED_EUR, "Code": "GBP", "Name": "Pound"}])
    gbp = Currency.objects.get(code="GBP")
    assert gbp.legacy_id == "2"
    assert gbp.is_active is False


@pytest.mark.django_db
def test_deleted_by_only_counts_as_deleted() -> None:
    _load([{**LIVE_EUR, "DeletedBy": "admin"}])
    assert Currency.objects.get(code="EUR").is_active is False


@pytest.mark.django_db
@pytest.mark.parametrize("order", ["deleted_first", "live_first"])
def test_live_row_claims_code_before_deleted_twin(order: str) -> None:
    rows = [DELETED_EUR, LIVE_EUR] if order == "deleted_first" else [LIVE_EUR, DELETED_EUR]
    report = _load(rows)
    eur = Currency.objects.get(code="EUR")
    assert eur.legacy_id == "3"
    assert eur.is_active is True
    assert eur.name == "Euro"
    assert report.skipped == 1


@pytest.mark.django_db
def test_live_row_displaces_a_deleted_twins_stale_claim() -> None:
    # A DB loaded before BUG-028 carries the deleted Id 2 on EUR.
    Currency.objects.create(code="EUR", name="Euro (old)", legacy_id="2", is_active=True)
    report = _load([DELETED_EUR, LIVE_EUR])
    eur = Currency.objects.get(code="EUR")
    assert eur.legacy_id == "3"
    assert eur.is_active is True
    assert report.skipped == 1


@pytest.mark.django_db
def test_seeded_currency_without_legacy_id_is_claimed() -> None:
    Currency.objects.create(code="EUR", name="Euro", symbol="€")
    report = _load([LIVE_EUR])
    eur = Currency.objects.get(code="EUR")
    assert eur.legacy_id == "3"
    assert report.updated == 1 and report.created == 0


@pytest.mark.django_db
def test_live_claim_is_never_displaced_by_a_different_live_row() -> None:
    Currency.objects.create(code="EUR", name="Euro", legacy_id="9")
    report = _load([LIVE_EUR])
    assert Currency.objects.get(code="EUR").legacy_id == "9"
    assert report.skipped == 1


@pytest.mark.django_db
def test_rerun_is_idempotent() -> None:
    _load([DELETED_EUR, LIVE_EUR])
    report = _load([DELETED_EUR, LIVE_EUR])
    assert Currency.objects.filter(code="EUR").count() == 1
    assert Currency.objects.get(code="EUR").legacy_id == "3"
    assert report.updated == 1 and report.skipped == 1 and report.created == 0


@pytest.mark.django_db
@pytest.mark.parametrize("code", ["HTFG", "RS", "", None, "E1R"])
def test_junk_codes_are_skipped(code: str | None) -> None:
    report = _load([{**LIVE_EUR, "Id": 4, "Code": code}])
    assert report.skipped == 1
    assert not Currency.objects.exists()


@pytest.mark.django_db
def test_code_is_normalised_and_fields_trimmed() -> None:
    _load([{"Id": 1, "Name": "  ", "Code": " gbp ", "Symbol": " £ "}])
    gbp = Currency.objects.get(code="GBP")
    assert gbp.name == "GBP"
    assert gbp.symbol == "£"


def test_legacy_query_selects_deletion_columns() -> None:
    query = CurrencyLoader().legacy_query
    assert "DeletedAt" in query
    assert "DeletedBy" in query
