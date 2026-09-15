"""ExtraLoader (GAP-107): legacy `VillaSeasonRate` extras (`IsExTra = 1`)
→ property-scoped opt-in `pricing.Extra` catalogue rows.

Transform tests on hand-rolled dict fixtures; `django_db` because the
transform resolves the Property and Currency FKs.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from data_migration.base import LoadReport
from data_migration.loaders.extras import ExtraLoader
from pricing.enums import ExtraCalc, ExtraKind
from pricing.factories import RatePeriodFactory, RatePlanFactory
from pricing.models.currency import Currency
from pricing.models.extra import Extra
from pricing.models.rate import RatePlan
from properties.models.geo import Country, Region
from properties.models.property import Property
from properties.models.settings import PropertySettings


@pytest.fixture
def eur(db: None) -> Currency:
    return Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="1")


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound", symbol="£", legacy_id="2")


@pytest.fixture
def villa(db: None) -> Property:
    country = Country.objects.get(iso2="GB")
    region = Region.objects.create(country=country, name="Cornwall", slug="cornwall")
    return Property.objects.create(
        name="P", display_name="P", slug="p", region=region, legacy_id="900"
    )


def _row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "ID": 7,
        "VillaId": 900,
        "Name": "Private chef",
        "Description": "Per stay, on request",
        "Price": Decimal("450.00"),
        "CurrencyId": 0,
    }
    row.update(overrides)
    return row


def _transform(row: dict[str, Any]) -> dict[str, Any]:
    kwargs = ExtraLoader().transform(row)
    assert kwargs is not None
    return kwargs


def _load(loader: ExtraLoader, rows: list[dict[str, Any]]) -> LoadReport:
    report = LoadReport(loader=loader.name)
    loader._load_rows(rows, report)
    return report


def test_query_selects_only_live_extras() -> None:
    query = ExtraLoader.legacy_query
    assert "IsExTra = 1" in query
    assert "DeletedAt IS NULL" in query
    assert ExtraLoader.legacy_pk_column == "ID"


@pytest.mark.django_db
def test_transform_maps_the_documented_opt_in_defaults(villa: Property, eur: Currency) -> None:
    kwargs = _transform(_row())
    assert kwargs["property"] == villa
    assert kwargs["name"] == "Private chef"
    assert kwargs["description"] == "Per stay, on request"
    assert kwargs["kind"] == ExtraKind.OTHER
    assert kwargs["calc"] == ExtraCalc.FIXED_PER_STAY
    assert kwargs["amount"] == Decimal("450.00")
    assert kwargs["currency"] == eur
    assert kwargs["is_mandatory"] is False
    assert kwargs["commissionable"] is True
    assert kwargs["applies_from"] is None and kwargs["applies_to"] is None
    assert kwargs["min_party"] is None and kwargs["max_party"] is None
    assert kwargs["is_active"] is True


@pytest.mark.django_db
def test_name_falls_back_to_description_then_id_and_truncates(
    villa: Property, eur: Currency
) -> None:
    assert _transform(_row(Name="  ", Description="Cot hire"))["name"] == "Cot hire"
    assert _transform(_row(Name=None, Description=""))["name"] == "Extra 7"
    assert len(_transform(_row(Name="x" * 300))["name"]) == 128


@pytest.mark.django_db
def test_null_price_ports_as_zero(villa: Property, eur: Currency) -> None:
    assert _transform(_row(Price=None))["amount"] == Decimal("0")


@pytest.mark.django_db
def test_currency_from_legacy_currency_id_when_set(
    villa: Property, eur: Currency, gbp: Currency
) -> None:
    assert _transform(_row(CurrencyId=2))["currency"] == gbp


@pytest.mark.django_db
def test_currency_falls_back_to_the_property_chain(
    villa: Property, eur: Currency, gbp: Currency
) -> None:
    # `CurrencyId = 0` on every legacy extra (2022 fold): resolve the way
    # the engine does — preferred live plan, then settings, then EUR — so
    # the extra lands in the currency quotes are built in.
    PropertySettings.objects.update_or_create(property=villa, defaults={"currency": eur})
    today = timezone.localdate()
    RatePeriodFactory(
        plan=RatePlanFactory(property=villa, currency=gbp),
        date_from=today - timedelta(days=1),
        date_to=today + timedelta(days=30),
    )
    assert _transform(_row())["currency"] == gbp

    RatePlan.objects.all().delete()
    assert _transform(_row())["currency"] == eur


@pytest.mark.django_db
def test_unknown_villa_is_skipped(eur: Currency) -> None:
    assert ExtraLoader().transform(_row(VillaId=999)) is None


@pytest.mark.django_db
def test_no_resolvable_currency_is_skipped(villa: Property) -> None:
    # No plan, no settings currency, and no EUR row at all.
    assert Currency.objects.count() == 0
    assert ExtraLoader().transform(_row()) is None


@pytest.mark.django_db
def test_load_is_idempotent_keyed_on_legacy_id_with_dense_sort_order(
    villa: Property, eur: Currency
) -> None:
    loader = ExtraLoader()
    first = _load(loader, [_row(ID=8, Name="Cot hire", Price=Decimal("30")), _row()])
    assert (first.created, first.updated) == (2, 0)

    second = _load(loader, [_row(Price=Decimal("500.00")), _row(ID=8, Name="Cot hire")])
    assert (second.created, second.updated) == (0, 2)

    extras = {e.legacy_id: e for e in Extra.objects.filter(property=villa)}
    assert set(extras) == {"7", "8"}
    assert extras["7"].amount == Decimal("500.00")
    assert extras["7"].currency == eur
    assert extras["7"].applies_from is None
    # Legacy creation order (by ID) as a dense 0..n rank per villa, whatever
    # order the cursor yields the rows in.
    assert (extras["7"].sort_order, extras["8"].sort_order) == (0, 1)


@pytest.mark.django_db
def test_rerun_refreshes_legacy_fields_but_keeps_staff_refinements(
    villa: Property, eur: Currency, gbp: Currency
) -> None:
    """Staff refine kind/calc/window/activity/currency in the SPA; an upsert
    onto an existing row may only touch what legacy can change."""
    loader = ExtraLoader()
    _load(loader, [_row()])
    Extra.objects.filter(legacy_id="7").update(
        kind=ExtraKind.CLEANING,
        calc=ExtraCalc.FIXED_PER_NIGHT,
        is_mandatory=True,
        applies_from=date(2026, 6, 1),
        applies_to=date(2026, 9, 30),
        min_party=2,
        sort_order=5,
        is_active=False,
        currency=gbp,
    )

    report = _load(loader, [_row(Name="Private chef (new)", Price=Decimal("475"))])
    assert (report.created, report.updated) == (0, 1)
    extra = Extra.objects.get(legacy_id="7")
    assert extra.name == "Private chef (new)"
    assert extra.amount == Decimal("475")
    assert extra.kind == ExtraKind.CLEANING
    assert extra.calc == ExtraCalc.FIXED_PER_NIGHT
    assert extra.is_mandatory is True
    assert (extra.applies_from, extra.applies_to) == (date(2026, 6, 1), date(2026, 9, 30))
    assert extra.min_party == 2
    assert extra.sort_order == 5
    assert extra.is_active is False
    assert extra.currency == gbp


@pytest.mark.django_db
def test_full_run_retires_extras_legacy_deleted_since(villa: Property, eur: Currency) -> None:
    loader = ExtraLoader()
    _load(loader, [_row(), _row(ID=8, Name="Cot hire")])
    Extra.objects.create(  # staff-created: never touched by the sweep
        property=villa,
        name="Late check-out",
        kind=ExtraKind.OTHER,
        calc=ExtraCalc.FIXED_PER_STAY,
        amount=Decimal("50"),
        currency=eur,
    )

    _load(loader, [_row()])  # legacy soft-deleted 8: gone from the result set
    assert Extra.objects.get(legacy_id="8").is_active is False
    assert Extra.objects.get(legacy_id="7").is_active is True
    assert Extra.objects.get(name="Late check-out").is_active is True
