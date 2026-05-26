"""factory-boy factories for the `pricing` app.

The rate chain (RatePlan -> RateCard -> RateRule) defaults to a wide window
straddling today so `PricingEngine.quote()` finds a rule for any near-future
stay the seeder generates instead of raising `NoRateAvailable`.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from pricing import models
from pricing.enums import DiscountKind, ExtraCalc, ExtraKind, RuleKind
from properties.factories import RUN_TOKEN, PropertyFactory

# Wide enough that generated stays (a few months out) always land inside it.
_WINDOW_FROM = date.today() - timedelta(days=30)
_WINDOW_TO = date.today() + timedelta(days=400)

_CURRENCIES = [
    ("GBP", "Pound sterling", "£"),
    ("EUR", "Euro", "€"),
    ("USD", "US dollar", "$"),
]


class CurrencyFactory(DjangoModelFactory):
    class Meta:
        model = models.Currency
        django_get_or_create = ("code",)

    class Params:
        spec = factory.Iterator(_CURRENCIES)

    code = factory.LazyAttribute(lambda o: o.spec[0])
    name = factory.LazyAttribute(lambda o: o.spec[1])
    symbol = factory.LazyAttribute(lambda o: o.spec[2])


class RatePlanFactory(DjangoModelFactory):
    class Meta:
        model = models.RatePlan

    property = factory.SubFactory(PropertyFactory)
    currency = factory.SubFactory(CurrencyFactory)
    name = factory.Sequence(lambda n: f"Standard rates {n}")
    effective_from = _WINDOW_FROM
    effective_to = _WINDOW_TO
    is_active = True


class RateCardFactory(DjangoModelFactory):
    class Meta:
        model = models.RateCard

    plan = factory.SubFactory(RatePlanFactory)
    name = "Default"
    min_nights = 1
    sort_order = 0
    is_active = True


class RateRuleFactory(DjangoModelFactory):
    class Meta:
        model = models.RateRule

    card = factory.SubFactory(RateCardFactory)
    date_from = _WINDOW_FROM
    date_to = _WINDOW_TO
    min_party = 1
    max_party = 30
    nightly = factory.Iterator([Decimal("250.00"), Decimal("400.00"), Decimal("650.00")])
    is_approved = True
    is_poa = False


class DiscountFactory(DjangoModelFactory):
    class Meta:
        model = models.Discount

    property = factory.SubFactory(PropertyFactory)
    name = factory.Sequence(lambda n: f"Early bird {n}")
    code = factory.Sequence(lambda n: f"EARLY-{RUN_TOKEN}-{n}")
    rule_kind = RuleKind.EARLY_BIRD
    kind = DiscountKind.PERCENT
    amount = Decimal("10.00")
    valid_from = _WINDOW_FROM
    valid_to = _WINDOW_TO


class FxRateFactory(DjangoModelFactory):
    """One FX edge per (base, quote, as_of). Defaults to today so additive
    same-day reruns must pass `as_of=` explicitly to avoid the unique
    constraint."""

    class Meta:
        model = models.FxRate
        django_get_or_create = ("base", "quote", "as_of")

    base = factory.SubFactory(CurrencyFactory, spec=("GBP", "Pound sterling", "£"))
    quote = factory.SubFactory(CurrencyFactory, spec=("EUR", "Euro", "€"))
    as_of = factory.LazyFunction(date.today)
    rate = Decimal("1.17")


class ExtraFactory(DjangoModelFactory):
    class Meta:
        model = models.Extra

    property = factory.SubFactory(PropertyFactory)
    currency = factory.SubFactory(CurrencyFactory)
    name = factory.Sequence(lambda n: f"Cleaning fee {n}")
    kind = ExtraKind.CLEANING
    calc = ExtraCalc.FIXED_PER_STAY
    amount = Decimal("150.00")
    is_mandatory = True
