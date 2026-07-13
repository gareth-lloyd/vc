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
from properties.models.property import Property, PropertyCategory
from properties.models.settings import PropertySettings


@pytest.fixture
def loaded_property(db: None) -> Property:
    country = Country.objects.get(iso2="GB")
    region = Region.objects.create(country=country, name="Cornwall", slug="cornwall")
    cat = PropertyCategory.objects.create(name="Villa", slug="villa")
    return Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        category=cat,
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


@pytest.mark.django_db
def test_transform_drops_inclusion_keeps_notes(loaded_property: Property) -> None:
    """GAP-037: the loader no longer writes inclusion onto RatePlan (it moves to
    PropertyService); operator `notes` stays on the plan."""
    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    kwargs = RatePlanLoader().transform(
        _row(CurrencyId=3, Notes="Owner-negotiated.", Inclusion="Private chef included.")
    )
    assert kwargs is not None
    assert "inclusion" not in kwargs
    assert kwargs["notes"] == "Owner-negotiated."


@pytest.mark.django_db
def test_process_row_emits_property_service_from_inclusion(loaded_property: Property) -> None:
    """GAP-037: a season with an Inclusion blurb materialises one date-banded
    PropertyService keyed `<season>:svc`, idempotent across re-runs."""
    from data_migration.base import LoadReport
    from properties.models import PropertyService

    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    row = _row(
        ID=1,
        CurrencyId=3,
        Inclusion="Private chef included.",
        DateFrom=date(2025, 6, 1),
        DateTo=date(2025, 8, 31),
    )
    loader = RatePlanLoader()
    loader._process_row(row, LoadReport(loader="rate_plan"))
    loader._process_row(row, LoadReport(loader="rate_plan"))  # re-run: still one

    svc = PropertyService.objects.get(legacy_id="1:svc")
    assert svc.property == loaded_property
    assert svc.copy == "Private chef included."
    assert svc.applies_from == date(2025, 6, 1)
    assert svc.applies_to == date(2025, 8, 31)
    assert svc.is_active is True


@pytest.mark.django_db
def test_process_row_no_service_when_plan_unresolved(loaded_property: Property) -> None:
    """An Inclusion on a season whose plan never materialises (villa doesn't
    resolve → transform returns None) must not leave an orphan PropertyService."""
    from data_migration.base import LoadReport
    from properties.models import PropertyService

    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    loader = RatePlanLoader()
    loader._process_row(
        _row(ID=3, VillaId=999999, CurrencyId=3, Inclusion="Chef included."),
        LoadReport(loader="rate_plan"),
    )

    assert not PropertyService.objects.filter(legacy_id="3:svc").exists()


@pytest.mark.django_db
def test_process_row_no_service_when_inclusion_blank(loaded_property: Property) -> None:
    from data_migration.base import LoadReport
    from properties.models import PropertyService

    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    loader = RatePlanLoader()
    loader._process_row(_row(ID=2, CurrencyId=3, Inclusion=None), LoadReport(loader="rate_plan"))

    assert not PropertyService.objects.filter(legacy_id="2:svc").exists()


@pytest.mark.django_db
def test_transform_stamps_price_basis_gross_explicitly(loaded_property: Property) -> None:
    """SMELL-021: legacy has no per-villa NET/GROSS signal (RatesModel.Calculate
    always treats the entered rate as the guest-facing gross and derives net by
    subtraction), so every imported plan is stamped GROSS *explicitly* — the
    basis must be a loader decision, never the model default riding along."""
    from properties.enums import PriceBasis

    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    kwargs = RatePlanLoader().transform(_row(CurrencyId=3))
    assert kwargs is not None
    assert kwargs["price_basis"] == PriceBasis.GROSS


@pytest.mark.django_db
def test_fallback_ignores_previously_loaded_plans(loaded_property: Property) -> None:
    """Re-run convergence: the fallback must not read the RatePlan table this
    loader populates. A run-1 mis-stamp (EUR) would otherwise re-resolve from
    itself forever; a since-fixed PropertySettings (GBP) must win instead."""
    from pricing.models.rate import RatePlan

    gbp = Currency.objects.create(code="GBP", name="Pound sterling", symbol="£", legacy_id="1")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    RatePlan.objects.create(
        property=loaded_property,
        name="High Season",
        currency=eur,  # the run-1 stamp the re-run must NOT echo
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 12, 31),
        legacy_id="1",
    )
    PropertySettings.objects.create(property=loaded_property, currency=gbp)
    kwargs = RatePlanLoader().transform(_row())
    assert kwargs is not None
    assert kwargs["currency"] == gbp
