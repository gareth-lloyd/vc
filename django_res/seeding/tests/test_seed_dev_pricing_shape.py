"""Pricing-shape contract: mixed/chaos villas must price like the legacy prod
snapshot — per-currency log-normal price levels with a long tail (not the
factory's flat 250/400/650 iterator), a Low/Mid/Peak seasonal period structure
with gap-free coverage, near-universal percentage commission, rare discounts,
and occasional occupancy bands / second-currency plans. `happy` keeps the
legacy one-period / one-rule / universal-discount shape byte-for-byte.

These run against an isolated transactional DB (no accumulation from other
tests), so the per-run distribution can be asserted directly.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from core.exceptions import PartyOutOfRange
from pricing.models import Discount, RatePlan, RateRule
from pricing.services.engine import PricingEngine
from properties.models import Property
from seeding._pricing_helpers import _PRICE_SHAPE, draw_base_nightly
from seeding.context import utc_today

_LEGACY_NIGHTLY = {Decimal("250.00"), Decimal("400.00"), Decimal("650.00")}


def _seed(profile: str, *, properties: int, bookings: int, seed: int) -> None:
    call_command(
        "seed_dev",
        "--properties",
        str(properties),
        "--bookings",
        str(bookings),
        "--profile",
        profile,
        "--seed",
        str(seed),
        stdout=StringIO(),
    )


def test_draw_base_nightly_matches_legacy_distribution() -> None:
    """Pure-helper check: draws stay inside the observed legacy clamps, land
    on 10s, and the median sits near the legacy per-currency median."""
    for code, (median, _sigma, lo, hi) in _PRICE_SHAPE.items():
        rng = random.Random(7)
        draws = sorted(draw_base_nightly(rng, code) for _ in range(400))
        assert all(lo <= d <= hi for d in draws), code
        assert all(d % 10 == 0 for d in draws), code
        observed_median = draws[200]
        assert median * Decimal("0.7") < observed_median < median * Decimal("1.4"), (
            code,
            observed_median,
        )
    # Unknown currencies fall back to the EUR shape.
    rng = random.Random(7)
    eur_lo, eur_hi = _PRICE_SHAPE["EUR"][2], _PRICE_SHAPE["EUR"][3]
    assert all(eur_lo <= draw_base_nightly(rng, "CHF") <= eur_hi for _ in range(50))


@pytest.mark.django_db(transaction=True)
def test_seed_dev_mixed_prices_realistically() -> None:
    """One mixed portfolio asserted from every pricing angle (a single run —
    each `transaction=True` test flushes + reseeds the whole DB):

    * realistic price levels: a wide, varied distribution, not the factory
      iterator;
    * Low/Mid/Peak seasonal periods with gap-free party-3 coverage across the
      full plan window (no NoRateAvailable for any stay the booking stages
      can generate);
    * occupancy bands on a few villas: contiguous brackets from 1 up to the
      (bumped) capacity, party-3 quotes succeed, an over-capacity party
      raises PartyOutOfRange;
    * near-universal commission, predominantly PERCENT in [12, 25];
    * discounts on only a minority of villas;
    * at least one villa pricing in two currencies.
    """
    _seed("mixed", properties=20, bookings=30, seed=42)
    today = utc_today()

    plans = list(RatePlan.objects.select_related("currency").prefetch_related("periods__rules"))
    assert plans

    # ---- Price levels: varied with a long tail, iterator values gone ----
    nightly_values = {r.nightly for r in RateRule.objects.all() if r.nightly is not None}
    assert len(nightly_values) >= 15, "expected a varied price distribution"
    assert not (_LEGACY_NIGHTLY & nightly_values), "factory iterator prices must be replaced"
    assert max(nightly_values) >= 5 * min(nightly_values), "expected a long-tailed spread"

    # ---- Seasonal structure + gap-free coverage ----
    # A season now spans several disjoint date segments, so a plan carries more
    # than three periods — but each is named for its season, every period holds
    # bands, and the whole window stays party-3 covered with no gaps.
    for plan in plans:
        periods = list(plan.periods.all())
        assert periods, plan
        assert {p.name for p in periods} <= {"Low", "Mid", "Peak"}, plan
        assert all(p.rules.exists() for p in periods), plan
        assert plan.effective_to is not None
        day = plan.effective_from
        while day <= plan.effective_to:
            covering = [p for p in periods if p.date_from <= day <= p.date_to]
            assert any(r.min_party <= 3 <= r.max_party for p in covering for r in p.rules.all()), (
                f"plan {plan.pk} has no party-3 rule covering {day}"
            )
            day += timedelta(days=14)

    # ---- Occupancy bands on a few villas ----
    banded_props = []
    for plan in plans:
        for period in plan.periods.all():
            brackets = {(r.min_party, r.max_party) for r in period.rules.all()}
            if len(brackets) > 1:
                banded_props.append(plan.property)
                ordered = sorted(brackets)
                assert ordered[0][0] == 1, ordered
                tops = [b[1] for b in ordered]
                starts = [b[0] for b in ordered[1:]]
                assert starts == [t + 1 for t in tops[:-1]], f"non-contiguous: {ordered}"
                assert tops[-1] == plan.property.capacity.guests >= 10, ordered
                break
    assert banded_props, "expected at least one occupancy-banded villa"
    prop = banded_props[0]
    quote_from = _aligned(prop, today + timedelta(days=45))
    quote = PricingEngine.quote(
        property=prop, date_from=quote_from, date_to=quote_from + timedelta(days=7), party=3
    )
    assert quote.total > 0
    with pytest.raises(PartyOutOfRange):
        PricingEngine.quote(
            property=prop,
            date_from=quote_from,
            date_to=quote_from + timedelta(days=7),
            party=prop.capacity.guests + 1,
        )

    # ---- Commission: near-universal, mostly percent in [12, 25] ----
    finances = [p.finance for p in Property.objects.all()]
    assert all(f.commission_calculation_type for f in finances)
    percents = [
        f.commission_amount
        for f in finances
        if f.commission_calculation_type == "percent" and f.commission_amount is not None
    ]
    assert len(percents) >= 0.7 * len(finances), "commission should be predominantly percent"
    assert all(Decimal("12") <= amount <= Decimal("25") for amount in percents)

    # ---- Discounts: rare, not universal ----
    assert Discount.objects.count() < Property.objects.count() / 2

    # ---- Second currency on at least one villa ----
    two_currency = [
        p for p in Property.objects.all() if len({pl.currency_id for pl in p.rate_plans.all()}) > 1
    ]
    assert two_currency, "expected at least one villa pricing in two currencies"


def _aligned(prop: Property, day: date) -> date:
    """Advance `day` onto the villa's changeover weekday, if it has one."""
    from properties.services.changeover import ChangeoverService

    weekday = ChangeoverService.required_weekday(prop, day)
    if weekday is None:
        return day
    return day + timedelta(days=(weekday - day.weekday()) % 7)


@pytest.mark.django_db(transaction=True)
def test_seed_dev_happy_keeps_legacy_pricing_shape() -> None:
    """The happy profile keeps the legacy shape: one period / one 1-30 rule per
    plan, iterator prices, a discount on every villa, no blanket commission."""
    _seed("happy", properties=4, bookings=6, seed=42)
    for plan in RatePlan.objects.prefetch_related("periods__rules"):
        periods = list(plan.periods.all())
        assert len(periods) == 1, plan
        rules = list(periods[0].rules.all())
        assert len(rules) == 1, plan
        assert rules[0].nightly in _LEGACY_NIGHTLY
        assert (rules[0].min_party, rules[0].max_party) == (1, 30)
    # Every properties-stage villa gets a discount (showcase villas minted by
    # dashboard_activity never did, in any profile — hence ==4, not ==count).
    assert Discount.objects.count() == 4
    finances = [p.finance for p in Property.objects.all()]
    # Only the owner-contact factory hook sets commission on happy.
    assert {f.commission_amount for f in finances} <= {None, Decimal("12.50"), Decimal("500.00")}
