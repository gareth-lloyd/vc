"""`rateplan_one_active_per_regime` (GAP-110 U4): at most one *active* plan
per (property, currency, price_basis) — the regime bucket is unique."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from pricing.models import Currency, RatePlan
from properties.enums import PriceBasis
from properties.models import Property


def _plan(property_: Property, currency: Currency, **overrides: object) -> RatePlan:
    kwargs: dict[str, object] = {
        "property": property_,
        "name": "Rates",
        "currency": currency,
    }
    kwargs.update(overrides)
    return RatePlan.objects.create(**kwargs)


@pytest.mark.django_db
def test_second_active_plan_in_a_regime_is_refused(property_: Property, gbp: Currency) -> None:
    _plan(property_, gbp)
    with (
        pytest.raises(IntegrityError, match="rateplan_one_active_per_regime"),
        transaction.atomic(),
    ):
        _plan(property_, gbp, name="Duplicate")


@pytest.mark.django_db
def test_inactive_sibling_is_allowed(property_: Property, gbp: Currency) -> None:
    _plan(property_, gbp)
    _plan(property_, gbp, name="Retired", is_active=False)
    _plan(property_, gbp, name="Older", is_active=False)


@pytest.mark.django_db
def test_other_basis_and_other_currency_are_separate_regimes(
    property_: Property, gbp: Currency, usd: Currency
) -> None:
    _plan(property_, gbp)
    _plan(property_, gbp, name="Net", price_basis=PriceBasis.NET)
    _plan(property_, usd, name="USD")


@pytest.mark.django_db
def test_reactivating_into_an_occupied_regime_is_refused(
    property_: Property, gbp: Currency
) -> None:
    _plan(property_, gbp)
    retired = _plan(property_, gbp, name="Retired", is_active=False)
    retired.is_active = True
    with (
        pytest.raises(IntegrityError, match="rateplan_one_active_per_regime"),
        transaction.atomic(),
    ):
        retired.save()


@pytest.mark.django_db
def test_full_clean_reports_the_occupied_regime(property_: Property, gbp: Currency) -> None:
    """Admin/forms path: `full_clean` surfaces the constraint as a
    non-field error before the database refuses the write."""
    _plan(property_, gbp)
    duplicate = RatePlan(property=property_, name="Duplicate", currency=gbp)
    with pytest.raises(ValidationError) as excinfo:
        duplicate.full_clean()
    assert "already has an active plan for this currency and price basis" in str(excinfo.value)


@pytest.mark.django_db
def test_migration_retires_only_season_keyed_legacy_plans(
    property_: Property, gbp: Currency, usd: Currency
) -> None:
    """`0011` deactivates pre-regroup loader rows (legacy-keyed by season id)
    so the constraint can land on a pre-U0 DB; regime-keyed and hand-made
    plans are untouched."""
    from importlib import import_module

    from django.apps import apps

    migration = import_module("pricing.migrations.0011_rateplan_one_active_per_regime")
    retire_season_keyed_plans = migration.retire_season_keyed_plans

    season_keyed = _plan(property_, gbp, name="High Season", legacy_id="42")
    regime = _plan(property_, usd, name="USD rates", legacy_id="villa:900:USD")
    hand_made = _plan(property_, gbp, name="Staff", price_basis=PriceBasis.NET)

    retire_season_keyed_plans(apps, None)

    assert not RatePlan.objects.get(pk=season_keyed.pk).is_active
    assert RatePlan.objects.get(pk=regime.pk).is_active
    assert RatePlan.objects.get(pk=hand_made.pk).is_active
