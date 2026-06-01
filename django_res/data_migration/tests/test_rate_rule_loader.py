from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from data_migration.loaders.pricing import RateRuleLoader
from pricing.models.currency import Currency
from pricing.models.rate import RateCard, RatePlan
from properties.models.capacity import PropertyCapacity
from properties.models.geo import Country, Region
from properties.models.property import Property, PropertyCategory, PropertyGroup


@pytest.fixture
def loaded_property(db: None) -> Property:
    country = Country.objects.get(iso2="GB")
    region = Region.objects.create(country=country, name="Cornwall", slug="cornwall")
    cat = PropertyCategory.objects.create(name="Villa", slug="villa")
    group = PropertyGroup.objects.create(name="G")
    prop = Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        category=cat,
        group=group,
        region=region,
    )
    PropertyCapacity.objects.create(property=prop, guests=8)
    return prop


@pytest.fixture
def loaded_card(loaded_property: Property) -> RateCard:
    currency = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    plan = RatePlan.objects.create(
        property=loaded_property,
        name="High",
        currency=currency,
        effective_from=date(2025, 1, 1),
        legacy_id="42",
    )
    return RateCard.objects.create(plan=plan, name="default", legacy_id="42")


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "ID": 1,
        "VillaId": None,
        "SeasonId": 42,
        "CurrencyId": 2,
        "FromDate": date(2025, 6, 1),
        "ToDate": date(2025, 6, 14),
        "PartySize": None,
        "IsPOA": False,
        "WeeklyPrice": Decimal("1000"),
        "NightlyPrice": None,
        "Price": None,
        "PriceType": 1,
        "IsExTra": False,
        "IsApprove": True,
        "IsAvailable": True,
        "Description": "Peak",
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
def test_transform_uses_capacity_when_party_size_missing(loaded_card: RateCard) -> None:
    kwargs = RateRuleLoader().transform(_row(PartySize=None))
    assert kwargs is not None
    assert kwargs["min_party"] == 1
    assert kwargs["max_party"] == 8


@pytest.mark.django_db
def test_transform_skips_when_card_missing() -> None:
    assert RateRuleLoader().transform(_row(SeasonId=999)) is None


@pytest.mark.django_db
def test_transform_skips_inverted_date_range(loaded_card: RateCard) -> None:
    assert (
        RateRuleLoader().transform(
            _row(FromDate=date(2025, 6, 14), ToDate=date(2025, 6, 1)),
        )
        is None
    )


@pytest.mark.django_db
def test_transform_skips_row_with_no_price(loaded_card: RateCard) -> None:
    assert (
        RateRuleLoader().transform(
            _row(WeeklyPrice=None, NightlyPrice=None, Price=None, IsPOA=False),
        )
        is None
    )


@pytest.mark.django_db
def test_transform_treats_price_as_nightly_when_alone(loaded_card: RateCard) -> None:
    kwargs = RateRuleLoader().transform(
        _row(WeeklyPrice=None, NightlyPrice=None, Price=Decimal("250")),
    )
    assert kwargs is not None
    assert kwargs["nightly"] == Decimal("250")


@pytest.mark.django_db
def test_transform_keeps_poa_rows(loaded_card: RateCard) -> None:
    kwargs = RateRuleLoader().transform(
        _row(WeeklyPrice=None, NightlyPrice=None, Price=None, IsPOA=True),
    )
    assert kwargs is not None
    assert kwargs["is_poa"] is True


@pytest.mark.django_db
def test_transform_poa_drops_price(loaded_card: RateCard) -> None:
    """POA wins over a numeric price — raterule_poa_excludes_price forbids both."""
    kwargs = RateRuleLoader().transform(
        _row(WeeklyPrice=Decimal("1000"), NightlyPrice=Decimal("200"), IsPOA=True),
    )
    assert kwargs is not None
    assert kwargs["is_poa"] is True
    assert kwargs["nightly"] is None
    assert kwargs["weekly"] is None


@pytest.mark.django_db
def test_transform_skips_zero_length_range(loaded_card: RateCard) -> None:
    assert (
        RateRuleLoader().transform(
            _row(FromDate=date(2025, 6, 1), ToDate=date(2025, 6, 1)),
        )
        is None
    )
