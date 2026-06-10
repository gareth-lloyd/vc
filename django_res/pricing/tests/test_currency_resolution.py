"""Canonical property-currency resolution (GAP-014).

Rule order: most recent rate plan → settings chain → EUR system default.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pytest

from pricing.models import Currency, RatePlan
from pricing.services.currency import default_currency, resolve_property_currency
from properties.models.settings import PropertySettings

if TYPE_CHECKING:
    from properties.models import Property


@pytest.fixture
def eur(db: None) -> Currency:
    return Currency.objects.create(code="EUR", name="Euro", symbol="€")


def _plan(property_: Property, currency: Currency, year: int, **kwargs: object) -> RatePlan:
    return RatePlan.objects.create(
        property=property_,
        name=f"Season {year}",
        currency=currency,
        effective_from=date(year, 1, 1),
        effective_to=date(year, 12, 31),
        **kwargs,
    )


@pytest.mark.django_db
def test_most_recent_plan_currency_wins(property_: Property, gbp: Currency, eur: Currency) -> None:
    """After a currency switch, the villa's *current* currency wins."""
    _plan(property_, gbp, 2024)
    _plan(property_, eur, 2025)
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_inactive_plans_are_ignored(property_: Property, gbp: Currency, eur: Currency) -> None:
    _plan(property_, eur, 2025, is_active=False)
    _plan(property_, gbp, 2024)
    assert resolve_property_currency(property_) == gbp


@pytest.mark.django_db
def test_same_effective_from_tie_breaks_on_newest_row(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    """Two covering plans sharing an effective_from resolve deterministically."""
    _plan(property_, gbp, 2025)
    _plan(property_, eur, 2025)  # newer pk wins the tie
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_future_dated_plan_does_not_dictate_todays_currency(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    """A pre-loaded next-year plan (scheduled currency switch) must not win
    over the plan actually in effect today."""
    _plan(property_, eur, 2025)
    _plan(property_, gbp, date.today().year + 1)
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_only_future_plans_fall_through_to_settings(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    _plan(property_, gbp, date.today().year + 1)
    PropertySettings.objects.create(property=property_, currency=eur)
    assert resolve_property_currency(property_) == eur


@pytest.mark.django_db
def test_settings_currency_when_no_plans(property_: Property, gbp: Currency, eur: Currency) -> None:
    PropertySettings.objects.create(property=property_, currency=gbp)
    assert resolve_property_currency(property_) == gbp


@pytest.mark.django_db
def test_group_settings_fallback_without_property_settings(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    group_settings = property_.group.settings
    group_settings.currency = gbp
    group_settings.save()
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
