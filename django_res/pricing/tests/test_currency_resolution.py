"""Canonical property-currency resolution (GAP-014, regime model per GAP-110).

Rule order: the active plan with an active period covering today → the plan
owning the latest period that ended before today → settings chain → EUR
system default. Ties between currencies prefer the settings currency, then
the lowest plan pk — never row recency (`RatePlan` carries no dates).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from pricing.models import Currency, RatePeriod, RatePlan
from pricing.services.currency import default_currency, resolve_property_currency
from pricing.tests.conftest import FROZEN_TODAY
from properties.models.settings import PropertySettings

if TYPE_CHECKING:
    from properties.models import Property

TODAY = date.fromisoformat(FROZEN_TODAY)


@pytest.fixture
def eur(db: None) -> Currency:
    return Currency.objects.create(code="EUR", name="Euro", symbol="€")


def _plan(
    property_: Property,
    currency: Currency,
    year: int,
    *,
    period_active: bool = True,
    **kwargs: object,
) -> RatePlan:
    """A plan with one full-year period (the period is what dates the regime)."""
    plan = RatePlan.objects.create(
        property=property_,
        name=f"Season {year} {currency.code}",
        currency=currency,
        **kwargs,
    )
    RatePeriod.objects.create(
        plan=plan,
        name=f"{year}",
        date_from=date(year, 1, 1),
        date_to=date(year, 12, 31),
        is_active=period_active,
    )
    return plan


@pytest.mark.django_db
def test_period_covering_today_wins(property_: Property, gbp: Currency, eur: Currency) -> None:
    """After a currency switch, the villa's *current* currency wins."""
    _plan(property_, gbp, TODAY.year - 1)
    _plan(property_, eur, TODAY.year)
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_latest_period_ending_before_today_wins_when_none_covers_today(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    _plan(property_, gbp, TODAY.year - 2)
    _plan(property_, eur, TODAY.year - 1)
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_inactive_plans_are_ignored(property_: Property, gbp: Currency, eur: Currency) -> None:
    _plan(property_, eur, TODAY.year, is_active=False)
    _plan(property_, gbp, TODAY.year - 1)
    assert resolve_property_currency(property_) == gbp


@pytest.mark.django_db
def test_inactive_periods_are_ignored(property_: Property, gbp: Currency, eur: Currency) -> None:
    _plan(property_, eur, TODAY.year, period_active=False)
    _plan(property_, gbp, TODAY.year - 1)
    assert resolve_property_currency(property_) == gbp


@pytest.mark.django_db
def test_two_currencies_covering_today_prefer_the_settings_currency(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    _plan(property_, gbp, TODAY.year)
    _plan(property_, eur, TODAY.year)
    PropertySettings.objects.create(property=property_, currency=eur)
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_two_currencies_covering_today_without_settings_pick_the_lowest_plan_pk(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    """Deterministic, and independent of which row was written last."""
    _plan(property_, gbp, TODAY.year)
    _plan(property_, eur, TODAY.year)
    assert resolve_property_currency(property_) == gbp


@pytest.mark.django_db
def test_future_dated_period_does_not_dictate_todays_currency(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    """A pre-loaded next-year plan (scheduled currency switch) must not win
    over the plan actually in effect today."""
    _plan(property_, eur, TODAY.year - 1)
    _plan(property_, gbp, TODAY.year + 1)
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_only_future_periods_fall_through_to_settings(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    _plan(property_, gbp, TODAY.year + 1)
    PropertySettings.objects.create(property=property_, currency=eur)
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_upcoming_period_beats_the_system_default_when_nothing_else_resolves(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    """A villa whose only rates are still to come, with no settings currency,
    resolves to that upcoming currency rather than EUR."""
    _plan(property_, gbp, TODAY.year + 2)
    _plan(property_, eur, TODAY.year + 1)  # the earliest upcoming period wins
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_periodless_plan_does_not_resolve(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    """A plan is a dateless bucket (GAP-110): without a period it says nothing
    about which currency is in effect."""
    RatePlan.objects.create(property=property_, name="Empty", currency=gbp)
    PropertySettings.objects.create(property=property_, currency=eur)
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_settings_currency_when_no_plans(property_: Property, gbp: Currency, eur: Currency) -> None:
    PropertySettings.objects.create(property=property_, currency=gbp)
    assert resolve_property_currency(property_) == gbp


@pytest.mark.django_db
def test_eur_default_when_nothing_configured(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_none_when_no_eur_row_exists(property_: Property, gbp: Currency) -> None:
    """Degenerate config: nothing resolvable and no EUR row — never `.first()`."""
    assert resolve_property_currency(property_) is None


@pytest.mark.django_db
def test_default_currency_is_eur_by_code_not_first_row(db: None) -> None:
    aud = Currency.objects.create(code="AUD", name="Australian dollar", symbol="$")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    assert Currency.objects.first() == aud  # ordering trap the helper must dodge
    assert default_currency() == eur
