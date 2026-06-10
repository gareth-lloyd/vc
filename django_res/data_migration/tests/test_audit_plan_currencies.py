"""`audit_plan_currencies` (GAP-014 step 0): the NULL-currency cohort gate.

The legacy side is pre-fetched rows (dict fixtures); the audit logic itself is
pure ORM, so it's tested directly without a live SQL Server.
"""

from __future__ import annotations

from datetime import date

import pytest

from data_migration.management.commands.audit_plan_currencies import (
    audit_null_currency_seasons,
    bookable_currency_mix,
)
from pricing.models.currency import Currency
from pricing.models.rate import RatePlan
from properties.models.geo import Country, Region
from properties.models.property import Property, PropertyCategory, PropertyGroup
from properties.models.settings import PropertySettings


@pytest.fixture
def prop(db: None) -> Property:
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


def _plan(prop: Property, currency: Currency, legacy_id: str = "42") -> RatePlan:
    return RatePlan.objects.create(
        property=prop,
        name="Season",
        currency=currency,
        effective_from=date(2026, 1, 1),
        legacy_id=legacy_id,
    )


def _row(season_id: int = 42, villa_currency_id: object = None) -> dict[str, object]:
    return {"ID": season_id, "VillaId": 900, "VillaCurrencyId": villa_currency_id}


@pytest.mark.django_db
def test_villa_rate_resolution_matching_plan_is_ok(prop: Property) -> None:
    gbp = Currency.objects.create(code="GBP", name="Pound", symbol="£", legacy_id="1")
    _plan(prop, gbp)
    result = audit_null_currency_seasons([_row(villa_currency_id=1)])
    assert result.blockers == []
    assert result.eur_defaults == []
    assert result.rows[0][2:] == ("villa-rates", "GBP", "OK")


@pytest.mark.django_db
def test_mismatched_plan_currency_is_a_blocker(prop: Property) -> None:
    Currency.objects.create(code="GBP", name="Pound", symbol="£", legacy_id="1")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    _plan(prop, eur)  # loaded EUR, but the villa's rows say GBP
    result = audit_null_currency_seasons([_row(villa_currency_id=1)])
    assert len(result.blockers) == 1
    assert "loaded EUR" in result.blockers[0]


@pytest.mark.django_db
def test_settings_resolution_is_ok_and_not_flagged(prop: Property) -> None:
    gbp = Currency.objects.create(code="GBP", name="Pound", symbol="£", legacy_id="1")
    PropertySettings.objects.create(property=prop, currency=gbp)
    _plan(prop, gbp)
    result = audit_null_currency_seasons([_row()])
    assert result.blockers == []
    assert result.eur_defaults == []
    assert result.rows[0][2] == "settings"


@pytest.mark.django_db
def test_group_settings_resolution_is_ok_not_a_false_blocker(prop: Property) -> None:
    """A villa with no PropertySettings row resolves via its group's settings
    (the same `settings_currency` chain the loader uses) — the audit must
    classify that as settings/OK, not expect the EUR default and BLOCKER."""
    gbp = Currency.objects.create(code="GBP", name="Pound", symbol="£", legacy_id="1")
    Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    group_settings = prop.group.settings
    group_settings.currency = gbp
    group_settings.save()
    _plan(prop, gbp)
    result = audit_null_currency_seasons([_row()])
    assert result.blockers == []
    assert result.rows[0][2:] == ("settings", "GBP", "OK")


@pytest.mark.django_db
def test_eur_default_remainder_is_listed_for_sign_off(prop: Property) -> None:
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    _plan(prop, eur)
    result = audit_null_currency_seasons([_row()])
    assert result.blockers == []
    assert len(result.eur_defaults) == 1
    assert "season 42" in result.eur_defaults[0]


@pytest.mark.django_db
def test_unloaded_season_counts_without_blocking(prop: Property) -> None:
    result = audit_null_currency_seasons([_row(season_id=999)])
    assert result.unloaded == 1
    assert result.blockers == []


@pytest.mark.django_db
def test_bookable_currency_mix_counts_distinct_properties(prop: Property) -> None:
    gbp = Currency.objects.create(code="GBP", name="Pound", symbol="£", legacy_id="1")
    _plan(prop, gbp, legacy_id="1")
    RatePlan.objects.create(
        property=prop,
        name="Open-ended",
        currency=gbp,
        effective_from=date(2025, 1, 1),
        legacy_id="2",
    )
    # A plan that ended before today must not count as bookable.
    RatePlan.objects.create(
        property=prop,
        name="Ended",
        currency=gbp,
        effective_from=date(2020, 1, 1),
        effective_to=date(2020, 12, 31),
        legacy_id="3",
    )
    assert bookable_currency_mix() == [("GBP", 2, 1)]
