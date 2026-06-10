"""QuotationLoader reference parity (GAP-006).

The legacy `QuotationNo` must carry forward as the canonical `Quotation.number`
and render `QVC{number}`, preserving exact legacy digits.
"""

from __future__ import annotations

import pytest

from data_migration.loaders.finance import QuotationLoader
from pricing.models.currency import Currency
from reservations.models.guest import Guest


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 10,
        "ClientDetailsId": 55,
        "AgentId": None,
        "CurrencyId": 2,
        "QuotationNo": 1805,
    }
    base.update(overrides)
    return base


@pytest.fixture
def _guest_and_currency(db: None) -> None:
    Guest.objects.create(
        first_name="Ada", last_name="Lovelace", email="ada@example.com", legacy_id="55"
    )
    Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="2")


@pytest.mark.django_db
def test_transform_maps_quotationno_to_number(_guest_and_currency: None) -> None:
    kwargs = QuotationLoader().transform(_row())
    assert kwargs is not None
    assert kwargs["number"] == 1805
    assert kwargs["reference"] == "QVC1805"


@pytest.mark.django_db
def test_transform_falls_back_to_id_for_reference_only(_guest_and_currency: None) -> None:
    """A missing QuotationNo keeps a numeric, customer-safe reference (`QVC{Id}`)
    but must NOT claim a `number` — the Id namespace overlaps real QuotationNos
    and the unique `number` column would collide."""
    kwargs = QuotationLoader().transform(_row(QuotationNo=None, Id=42))
    assert kwargs is not None
    assert "number" not in kwargs
    assert kwargs["reference"] == "QVC42"


@pytest.mark.django_db
def test_transform_treats_zero_quotationno_as_missing(_guest_and_currency: None) -> None:
    kwargs = QuotationLoader().transform(_row(QuotationNo=0, Id=42))
    assert kwargs is not None
    assert "number" not in kwargs
    assert kwargs["reference"] == "QVC42"


@pytest.mark.django_db
def test_missing_currency_resolves_via_first_line_property(_guest_and_currency: None) -> None:
    """GAP-014 step 0: a NULL line currency resolves through the first line's
    villa (settings chain), never `Currency.objects.first()`."""
    from properties.models.geo import Country, Region
    from properties.models.property import Property, PropertyCategory, PropertyGroup
    from properties.models.settings import PropertySettings

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
        legacy_id="900",
    )
    gbp = Currency.objects.get(code="GBP")
    PropertySettings.objects.create(property=prop, currency=gbp)
    kwargs = QuotationLoader().transform(_row(CurrencyId=None, FirstVillaId=900))
    assert kwargs is not None
    assert kwargs["currency"] == gbp


@pytest.mark.django_db
def test_missing_currency_terminal_default_is_eur_not_first_row(
    _guest_and_currency: None,
) -> None:
    Currency.objects.create(code="AUD", name="Australian dollar", symbol="$", legacy_id="9")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    kwargs = QuotationLoader().transform(_row(CurrencyId=None, FirstVillaId=None))
    assert kwargs is not None
    assert kwargs["currency"] == eur
