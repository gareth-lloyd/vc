"""Factory smoke tests for the pricing app."""

from __future__ import annotations

from datetime import date
from typing import cast

import pytest

from pricing import factories, models

pytestmark = pytest.mark.django_db


def test_currency_factory_get_or_create_is_idempotent() -> None:
    c1 = cast(models.Currency, factories.CurrencyFactory(spec=("GBP", "Pound sterling", "£")))
    c2 = cast(models.Currency, factories.CurrencyFactory(spec=("GBP", "Pound sterling", "£")))
    assert c1.pk == c2.pk
    assert models.Currency.objects.filter(code="GBP").count() == 1


def test_rate_rule_chain_covers_today() -> None:
    rule = cast(models.RateRule, factories.RateRuleFactory())
    assert rule.period.date_from <= date.today() <= rule.period.date_to
    assert rule.is_approved
    assert rule.nightly is not None
    # Chain is wired property -> plan -> period -> rule, one currency.
    assert rule.period.plan.property_id is not None
    assert rule.period.plan.currency_id is not None


def test_discount_and_extra_factories() -> None:
    discount = cast(models.Discount, factories.DiscountFactory())
    extra = cast(models.Extra, factories.ExtraFactory())
    assert discount.amount > 0
    assert extra.currency_id is not None


def test_fx_rate_factory_is_idempotent_on_same_day_edge() -> None:
    r1 = cast(models.FxRate, factories.FxRateFactory())
    r2 = cast(models.FxRate, factories.FxRateFactory())
    # `(base, quote, as_of)` is unique; second call must return the same row.
    assert r1.pk == r2.pk
