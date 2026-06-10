"""QuotationLoader reference parity (GAP-006).

The legacy `QuotationNo` must carry forward as the canonical `Quotation.number`
and render `QVC{number}`, preserving exact legacy digits.
"""

from __future__ import annotations

from datetime import date

import pytest

from data_migration.loaders.finance import QuotationLineLoader, QuotationLoader
from pricing.models.currency import Currency
from properties.models.geo import Country, Region
from properties.models.property import Property, PropertyCategory, PropertyGroup
from properties.models.settings import PropertySettings
from reservations.models.guest import Guest
from reservations.models.quotation import Quotation


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
def test_transform_returns_no_currency_key(_guest_and_currency: None) -> None:
    """GAP-014: the header has no currency — each line carries its own."""
    kwargs = QuotationLoader().transform(_row())
    assert kwargs is not None
    assert "currency" not in kwargs


def _line_row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Id": 77,
        "QuotationMasterId": 10,
        "VillaId": 900,
        "FromDate": date(2026, 6, 10),
        "ToDate": date(2026, 6, 17),
        "Price": 1400,
        "CurrencyId": 2,
        "IsManual": False,
    }
    base.update(overrides)
    return base


def _quotation_and_property() -> Property:
    """Build the Quotation (legacy_id=10) + Property (legacy_id=900) graph
    `QuotationLineLoader.transform` resolves against."""
    quotation = QuotationLoader().transform(_row())
    assert quotation is not None
    Quotation.objects.create(legacy_id="10", **quotation)
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


@pytest.mark.django_db
def test_line_currencyid_resolves_by_currency_legacy_id(_guest_and_currency: None) -> None:
    _quotation_and_property()
    gbp = Currency.objects.get(code="GBP")
    kwargs = QuotationLineLoader().transform(_line_row(CurrencyId=2))
    assert kwargs is not None
    assert kwargs["currency"] == gbp


@pytest.mark.django_db
def test_missing_currency_resolves_via_first_line_property(_guest_and_currency: None) -> None:
    """GAP-014: a NULL line CurrencyId resolves through the line's villa
    (settings chain), never `Currency.objects.first()`."""
    prop = _quotation_and_property()
    gbp = Currency.objects.get(code="GBP")
    PropertySettings.objects.create(property=prop, currency=gbp)
    kwargs = QuotationLineLoader().transform(_line_row(CurrencyId=None))
    assert kwargs is not None
    assert kwargs["currency"] == gbp


@pytest.mark.django_db
def test_missing_currency_terminal_default_is_eur_not_first_row(
    _guest_and_currency: None,
) -> None:
    _quotation_and_property()
    Currency.objects.create(code="AUD", name="Australian dollar", symbol="$", legacy_id="9")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    kwargs = QuotationLineLoader().transform(_line_row(CurrencyId=None))
    assert kwargs is not None
    assert kwargs["currency"] == eur


@pytest.mark.django_db
def test_missing_currency_unresolvable_skips_row(_guest_and_currency: None) -> None:
    """No row CurrencyId, no property chain, no EUR row — the line is skipped
    rather than guessed."""
    _quotation_and_property()
    kwargs = QuotationLineLoader().transform(_line_row(CurrencyId=None))
    assert kwargs is None
