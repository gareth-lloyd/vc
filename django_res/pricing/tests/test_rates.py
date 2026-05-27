"""Unit tests for `pricing.services.rates.pick_rule_for_night`.

The engine relies on three outcomes from the rate-picker per night:

* a matching rule was found — quote the night at that rule's nightly,
* rules cover the night but the party is outside every bracket — raise
  `PartyOutOfRange` (the legacy `09-departures.md` bug #2 regression),
* no rule on any card covers the night at all — raise `NoRateAvailable`.

Distinguishing the last two used to require a second nested loop
(`any_rule_covers_night`). The tagged-result API folds the disambiguation
into the single pass that already walks the cards-by-rules grid.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pricing.models import RateCard, RateRule
from pricing.services.rates import (
    NoCoverage,
    OutOfRange,
    Picked,
    pick_rule_for_night,
)


@pytest.mark.django_db
def test_pick_rule_returns_picked_with_matching_rule(card: RateCard) -> None:
    """A rule that covers both the night and the party returns `Picked`."""
    rule = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )

    result = pick_rule_for_night([card], {card.pk: [rule]}, night=date(2026, 6, 10), party=4)

    assert isinstance(result, Picked)
    assert result.card == card
    assert result.rule == rule


@pytest.mark.django_db
def test_pick_rule_returns_out_of_range_when_no_party_matches(card: RateCard) -> None:
    """Rules cover the night but the party falls outside every bracket."""
    common = {
        "card": card,
        "date_from": date(2026, 6, 1),
        "date_to": date(2026, 8, 31),
        "priority": 0,
    }
    rule_small = RateRule.objects.create(
        **common, min_party=1, max_party=8, nightly=Decimal("100.00")
    )
    rule_mid = RateRule.objects.create(
        **common, min_party=9, max_party=12, nightly=Decimal("250.00")
    )

    result = pick_rule_for_night(
        [card],
        {card.pk: [rule_small, rule_mid]},
        night=date(2026, 6, 10),
        party=20,
    )

    assert isinstance(result, OutOfRange)


@pytest.mark.django_db
def test_pick_rule_returns_no_coverage_when_no_rule_covers(card: RateCard) -> None:
    """No rule on any card covers the requested night."""
    rule = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )

    result = pick_rule_for_night([card], {card.pk: [rule]}, night=date(2026, 9, 1), party=4)

    assert isinstance(result, NoCoverage)


@pytest.mark.django_db
def test_pick_rule_returns_no_coverage_with_no_rules_at_all(card: RateCard) -> None:
    """An empty rules map is `NoCoverage`, not `OutOfRange`."""
    result = pick_rule_for_night([card], {card.pk: []}, night=date(2026, 6, 10), party=4)

    assert isinstance(result, NoCoverage)


@pytest.mark.django_db
def test_pick_rule_higher_priority_wins(card: RateCard) -> None:
    """Highest `priority` wins when multiple rules cover the same night."""
    wide = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        priority=0,
        nightly=Decimal("100.00"),
    )
    promo = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 15),
        min_party=1,
        max_party=8,
        priority=10,
        nightly=Decimal("300.00"),
    )

    result = pick_rule_for_night([card], {card.pk: [wide, promo]}, night=date(2026, 6, 12), party=4)

    assert isinstance(result, Picked)
    assert result.rule == promo
