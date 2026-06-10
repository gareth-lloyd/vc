"""Engine quotes without a currency argument (GAP-014 step 1).

Legacy parity: a quote with no currency prices in the covering rate plan's own
currency; the projection fallback resolves the villa's *current* currency
first (most recent plan), never a stale pre-switch one.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from core.exceptions import NoRateAvailable
from pricing.models import Currency, RateCard, RatePlan, RateRule
from pricing.services.engine import PricingEngine
from properties.models.settings import PropertySettings

if TYPE_CHECKING:
    from properties.models import Property


@pytest.fixture
def eur(db: None) -> Currency:
    return Currency.objects.create(code="EUR", name="Euro", symbol="€")


def _priced_plan(
    property_: Property,
    currency: Currency,
    year: int,
    *,
    nightly: str = "200.00",
) -> RatePlan:
    plan = RatePlan.objects.create(
        property=property_,
        name=f"Season {year} {currency.code}",
        currency=currency,
        effective_from=date(year, 1, 1),
        effective_to=date(year, 12, 31),
    )
    card = RateCard.objects.create(plan=plan, name="Default", sort_order=0)
    RateRule.objects.create(
        card=card,
        date_from=date(year, 1, 1),
        date_to=date(year, 12, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal(nightly),
    )
    return plan


@pytest.mark.django_db
def test_quote_without_currency_prices_in_plan_currency(property_: Property, gbp: Currency) -> None:
    _priced_plan(property_, gbp, 2026)
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        party=2,
    )
    assert quote.currency_code == "GBP"
    assert quote.breakdown["currency_code"] == "GBP"
    assert quote.total == Decimal("1400.00")


@pytest.mark.django_db
def test_explicit_currency_still_exact_matches(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    _priced_plan(property_, gbp, 2026)
    with pytest.raises(NoRateAvailable):
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 8),
            party=2,
            currency=eur,
            allow_projection=False,
        )


@pytest.mark.django_db
def test_two_covering_plans_most_recent_effective_from_wins(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    """An open-ended older GBP plan loses to a newer EUR plan covering the stay."""
    older = _priced_plan(property_, gbp, 2025)
    older.effective_to = None
    older.save(update_fields=["effective_to"])
    _priced_plan(property_, eur, 2026, nightly="300.00")
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        party=2,
    )
    assert quote.currency_code == "EUR"


@pytest.mark.django_db
def test_same_day_tie_prefers_settings_currency(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    _priced_plan(property_, eur, 2026, nightly="300.00")
    _priced_plan(property_, gbp, 2026)  # newest row — would win a bare pk tie-break
    PropertySettings.objects.create(property=property_, currency=eur)
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        party=2,
    )
    assert quote.currency_code == "EUR"


@pytest.mark.django_db
def test_projection_anchors_on_post_switch_currency(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    """GBP 2024 → EUR 2025: a currency-less 2026 quote projects from the EUR
    plan (the villa's current currency), not the stale GBP one."""
    _priced_plan(property_, gbp, 2024)
    _priced_plan(property_, eur, 2025, nightly="250.00")
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 5),
        date_to=date(2026, 6, 12),
        party=2,
    )
    assert quote.is_projected is True
    assert quote.currency_code == "EUR"
    assert quote.breakdown["projection"]["source_year"] == 2025


@pytest.mark.django_db
def test_projection_ignores_future_dated_plan_currency(
    property_: Property, gbp: Currency, eur: Currency
) -> None:
    """A scheduled currency switch (future-dated EUR plan) must not steer the
    projection currency for a stay before the switch: the GBP plan in effect
    today anchors the projection, where resolving EUR would find no anchor
    and raise NoRateAvailable for a perfectly priceable villa."""
    _priced_plan(property_, gbp, 2025)
    future = _priced_plan(property_, eur, 2026, nightly="300.00")
    future.effective_from = date(2026, 9, 1)  # after today (2026-06-10)
    future.save(update_fields=["effective_from"])
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 5),
        date_to=date(2026, 6, 12),
        party=2,
    )
    assert quote.is_projected is True
    assert quote.currency_code == "GBP"
    assert quote.breakdown["projection"]["source_year"] == 2025


@pytest.mark.django_db
def test_no_plans_at_all_raises_no_rate_available(property_: Property, eur: Currency) -> None:
    with pytest.raises(NoRateAvailable):
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 8),
            party=2,
        )
