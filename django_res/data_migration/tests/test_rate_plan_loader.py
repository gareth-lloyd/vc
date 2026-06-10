"""RatePlanLoader currency resolution (GAP-014 step 0).

A season whose legacy rate rows all have NULL/0 CurrencyId must resolve via
the villa's other non-NULL rows (`VillaCurrencyId`), then the canonical
settings → EUR chain — never the ordering-dependent `Currency.objects.first()`.
"""

from __future__ import annotations

from datetime import date

import pytest

from data_migration.loaders.pricing import RatePlanLoader
from pricing.models.currency import Currency
from properties.models.geo import Country, Region
from properties.models.property import Property, PropertyCategory, PropertyGroup
from properties.models.settings import PropertySettings


@pytest.fixture
def loaded_property(db: None) -> Property:
    country = Country.objects.get(iso2="GB")
    region = Region.objects.create(country=country, name="Cornwall", slug="cornwall")
    cat = PropertyCategory.objects.create(name="Villa", slug="villa")
    group = PropertyGroup.objects.create(name="G")
    return Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        category=cat,
        group=group,
        region=region,
        legacy_id="900",
    )


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ID": 1,
        "Name": "High Season",
        "VillaId": 900,
        "Notes": None,
        "Inclusion": None,
        "CurrencyId": None,
        "VillaCurrencyId": None,
        "DateFrom": date(2025, 1, 1),
        "DateTo": date(2025, 12, 31),
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_season_currency_used_when_present(loaded_property: Property) -> None:
    gbp = Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="1")
    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    kwargs = RatePlanLoader().transform(_row(CurrencyId=1, VillaCurrencyId=3))
    assert kwargs is not None
    assert kwargs["currency"] == gbp


@pytest.mark.django_db
def test_null_season_currency_infers_from_villa_rows(loaded_property: Property) -> None:
    gbp = Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="1")
    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    kwargs = RatePlanLoader().transform(_row(CurrencyId=None, VillaCurrencyId=1))
    assert kwargs is not None
    assert kwargs["currency"] == gbp


@pytest.mark.django_db
def test_null_currencies_fall_back_to_settings(loaded_property: Property) -> None:
    gbp = Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="1")
    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    PropertySettings.objects.create(property=loaded_property, currency=gbp)
    kwargs = RatePlanLoader().transform(_row())
    assert kwargs is not None
    assert kwargs["currency"] == gbp


@pytest.mark.django_db
def test_null_currencies_terminal_default_is_eur_not_first_row(
    loaded_property: Property,
) -> None:
    # AUD sorts (and was created) first — `.first()` would pick it.
    Currency.objects.create(code="AUD", name="Australian dollar", symbol="$", legacy_id="9")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    kwargs = RatePlanLoader().transform(_row())
    assert kwargs is not None
    assert kwargs["currency"] == eur


@pytest.mark.django_db
def test_row_skipped_when_nothing_resolves(loaded_property: Property) -> None:
    Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="1")
    # No EUR row, no settings, no usable legacy currency → skip, don't guess.
    assert RatePlanLoader().transform(_row()) is None
