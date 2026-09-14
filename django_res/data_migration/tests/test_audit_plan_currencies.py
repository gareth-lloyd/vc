"""`audit_plan_currencies` (GAP-014 step 0): the NULL-currency cohort gate.

The legacy side is pre-fetched rows (dict fixtures); the audit logic itself is
pure ORM, so it's tested directly without a live SQL Server.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from data_migration.management.commands.audit_plan_currencies import (
    audit_null_currency_seasons,
    bookable_currency_mix,
)
from pricing.models.currency import Currency
from pricing.models.rate import RatePeriod, RatePlan
from properties.enums import PriceBasis
from properties.models.geo import Country, Region
from properties.models.property import Property
from properties.models.settings import PropertySettings


@pytest.fixture
def prop(db: None) -> Property:
    country = Country.objects.get(iso2="GB")
    region = Region.objects.create(country=country, name="Cornwall", slug="cornwall")
    return Property.objects.create(
        name="P",
        display_name="P",
        slug="p",
        region=region,
        legacy_id="900",
    )


def _plan(prop: Property, currency: Currency, legacy_id: str | None = None) -> RatePlan:
    """The regime plan `RatePlanLoader` mints for villa 900 in `currency`."""
    return RatePlan.objects.create(
        property=prop,
        name=f"{currency.code} rates",
        currency=currency,
        effective_from=date(2026, 1, 1),
        legacy_id=legacy_id or f"villa:900:{currency.code}",
    )


def _row(
    season_id: int = 42, villa_id: int = 900, villa_currency_id: object = None
) -> dict[str, object]:
    return {"ID": season_id, "VillaId": villa_id, "VillaCurrencyId": villa_currency_id}


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
    """GAP-110: the villa's regime plans are keyed by currency, so "loaded under
    the wrong currency" means no `villa:900:GBP` plan exists while the villa
    has a plan in another currency."""
    Currency.objects.create(code="GBP", name="Pound", symbol="£", legacy_id="1")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    _plan(prop, eur)  # loaded EUR, but the villa's rows say GBP
    result = audit_null_currency_seasons([_row(villa_currency_id=1)])
    assert len(result.blockers) == 1
    assert "loaded EUR" in result.blockers[0]
    assert result.rows[0][2:] == ("villa-rates", "EUR", "BLOCKER")


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
def test_eur_default_remainder_is_listed_for_sign_off(prop: Property) -> None:
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", legacy_id="3")
    _plan(prop, eur)
    result = audit_null_currency_seasons([_row()])
    assert result.blockers == []
    assert len(result.eur_defaults) == 1
    assert "season 42" in result.eur_defaults[0]


@pytest.mark.django_db
def test_unloaded_season_counts_without_blocking(prop: Property) -> None:
    """A villa with no regime plan at all (unresolvable villa, rate-less
    seasons) is reported, not blocked."""
    result = audit_null_currency_seasons([_row(villa_id=999)])
    assert result.unloaded == 1
    assert result.blockers == []


@pytest.mark.django_db
def test_bookable_currency_mix_counts_distinct_properties(prop: Property) -> None:
    """GAP-110: bookable means an active period ending today or later — a
    plan whose only period has elapsed, or whose current period is
    withdrawn, does not count; the GROSS and NET buckets of one villa do."""
    gbp = Currency.objects.create(code="GBP", name="Pound", symbol="£", legacy_id="1")
    today = date.today()
    gross = _plan(prop, gbp)
    RatePeriod.objects.create(
        plan=gross, name="Current", date_from=today, date_to=today + timedelta(days=30)
    )
    net = RatePlan.objects.create(
        property=prop,
        name="Net rates",
        currency=gbp,
        price_basis=PriceBasis.NET,
        effective_from=date(2025, 1, 1),
        legacy_id="2",
    )
    RatePeriod.objects.create(
        plan=net,
        name="Next month",
        date_from=today + timedelta(days=31),
        date_to=today + timedelta(days=60),
    )
    # A plan whose periods all ended before today must not count as bookable
    # (its own currency, so a false positive would show up as a USD row).
    usd = Currency.objects.create(code="USD", name="Dollar", symbol="$", legacy_id="2")
    ended = RatePlan.objects.create(
        property=prop,
        name="Ended",
        currency=usd,
        effective_from=date(2020, 1, 1),
        legacy_id="3",
    )
    RatePeriod.objects.create(
        plan=ended, name="2020", date_from=date(2020, 1, 1), date_to=date(2020, 12, 31)
    )
    assert bookable_currency_mix() == [("GBP", 2, 1)]

    RatePeriod.objects.filter(plan=net).update(is_active=False)
    assert bookable_currency_mix() == [("GBP", 1, 1)]
