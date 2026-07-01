"""Tests for the GAP-056 Unit 2 period backfill.

`backfill_plan_periods` groups a plan's flat `RateRule`s (which historically
carried their own dates) onto disjoint `RatePeriod`s via `segment_card_rules`,
points every rule at its covering period, and fragments any ragged rule bisected
by a sibling band's boundary. Exercised here on "pre-migration"-shaped rows
(`period` still NULL), seeded with `bulk_create` so the transitional `save()`
shim doesn't pre-assign periods.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pricing.models import RateCard, RatePeriod, RatePlan, RateRule
from pricing.services.period_backfill import backfill_plan_periods


def _rule(card: RateCard, d_from: date, d_to: date, lo: int, hi: int, price: str) -> RateRule:
    return RateRule(
        card=card,
        date_from=d_from,
        date_to=d_to,
        min_party=lo,
        max_party=hi,
        nightly=Decimal(price),
    )


@pytest.mark.django_db
def test_backfill_non_ragged_creates_one_period_per_disjoint_rule(card: RateCard) -> None:
    RateRule.objects.bulk_create(
        [
            _rule(card, date(2026, 6, 1), date(2026, 6, 30), 1, 8, "200"),
            _rule(card, date(2026, 7, 1), date(2026, 7, 31), 1, 8, "300"),
        ]
    )

    backfill_plan_periods(RatePeriod, RateRule)

    periods = list(RatePeriod.objects.filter(plan=card.plan).order_by("date_from"))
    assert [(p.date_from, p.date_to) for p in periods] == [
        (date(2026, 6, 1), date(2026, 6, 30)),
        (date(2026, 7, 1), date(2026, 7, 31)),
    ]
    for rule in RateRule.objects.filter(card=card):
        assert rule.period is not None
        assert (rule.period.date_from, rule.period.date_to) == (rule.date_from, rule.date_to)


@pytest.mark.django_db
def test_backfill_sibling_bands_share_one_period(card: RateCard) -> None:
    """Same dates, disjoint party → one period holding both bands [H2]."""
    RateRule.objects.bulk_create(
        [
            _rule(card, date(2026, 6, 1), date(2026, 6, 30), 1, 8, "200"),
            _rule(card, date(2026, 6, 1), date(2026, 6, 30), 9, 12, "350"),
        ]
    )

    backfill_plan_periods(RatePeriod, RateRule)

    periods = RatePeriod.objects.filter(plan=card.plan)
    assert periods.count() == 1
    period = periods.get()
    assert set(RateRule.objects.filter(card=card).values_list("period_id", flat=True)) == {
        period.pk
    }


@pytest.mark.django_db
def test_backfill_ragged_fragments_into_single_day_period(card: RateCard) -> None:
    """Two bands sharing a boundary day segment into a single-day period.

    A [Jun1..Jun10] party 1-8, B [Jun10..Jun20] party 9-12 → three periods
    ([Jun1..Jun9], [Jun10..Jun10], [Jun11..Jun20]); each source rule fragments
    across the boundary. Proves the single-day fragment persists (relaxed CHECK).
    """
    RateRule.objects.bulk_create(
        [
            _rule(card, date(2026, 6, 1), date(2026, 6, 10), 1, 8, "200"),
            _rule(card, date(2026, 6, 10), date(2026, 6, 20), 9, 12, "350"),
        ]
    )

    backfill_plan_periods(RatePeriod, RateRule)

    periods = list(RatePeriod.objects.filter(plan=card.plan).order_by("date_from"))
    assert [(p.date_from, p.date_to) for p in periods] == [
        (date(2026, 6, 1), date(2026, 6, 9)),
        (date(2026, 6, 10), date(2026, 6, 10)),
        (date(2026, 6, 20 - 9), date(2026, 6, 20)),  # [Jun11..Jun20]
    ]
    # Every rule (originals + fragments) lands on a period; nothing orphaned.
    rules = RateRule.objects.filter(card=card)
    assert rules.count() == 4
    assert not rules.filter(period__isnull=True).exists()
    single_day = RatePeriod.objects.get(plan=card.plan, date_from=date(2026, 6, 10))
    assert single_day.date_from == single_day.date_to
    assert single_day.rules.count() == 2


@pytest.mark.django_db
def test_backfill_is_scoped_per_plan(card: RateCard) -> None:
    """Rules under different plans segment independently (no cross-plan periods)."""
    other_plan = RatePlan.objects.create(
        property=card.plan.property,
        name="Other",
        currency=card.plan.currency,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    other_card = RateCard.objects.create(plan=other_plan, name="Other", sort_order=0)
    RateRule.objects.bulk_create(
        [
            _rule(card, date(2026, 6, 1), date(2026, 6, 30), 1, 8, "200"),
            _rule(other_card, date(2026, 6, 1), date(2026, 6, 30), 1, 8, "500"),
        ]
    )

    backfill_plan_periods(RatePeriod, RateRule)

    assert RatePeriod.objects.filter(plan=card.plan).count() == 1
    assert RatePeriod.objects.filter(plan=other_plan).count() == 1
