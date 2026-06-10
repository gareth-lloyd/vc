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
def test_pick_rule_first_card_in_list_order_wins(card: RateCard) -> None:
    """Card order is the only cross-card precedence — even when a later
    card's rule is narrower (no specificity tie-break)."""
    second_card = RateCard.objects.create(plan=card.plan, name="Overlay", sort_order=1)
    wide = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    narrow = RateRule.objects.create(
        card=second_card,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 15),
        min_party=1,
        max_party=8,
        nightly=Decimal("300.00"),
    )

    result = pick_rule_for_night(
        [card, second_card],
        {card.pk: [wide], second_card.pk: [narrow]},
        night=date(2026, 6, 12),
        party=4,
    )

    assert isinstance(result, Picked)
    assert result.card == card
    assert result.rule == wide

    flipped = pick_rule_for_night(
        [second_card, card],
        {card.pk: [wide], second_card.pk: [narrow]},
        night=date(2026, 6, 12),
        party=4,
    )
    assert isinstance(flipped, Picked)
    assert flipped.rule == narrow


@pytest.mark.django_db
def test_pick_rule_falls_through_to_next_card_on_party_miss(card: RateCard) -> None:
    """A night-covering rule with the wrong party bracket on the first card
    must not shadow a matching rule on the next card — and must still count
    towards the OutOfRange/NoCoverage distinction."""
    second_card = RateCard.objects.create(plan=card.plan, name="Large groups", sort_order=1)
    small = RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    large = RateRule.objects.create(
        card=second_card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=9,
        max_party=12,
        nightly=Decimal("250.00"),
    )

    result = pick_rule_for_night(
        [card, second_card],
        {card.pk: [small], second_card.pk: [large]},
        night=date(2026, 6, 10),
        party=10,
    )

    assert isinstance(result, Picked)
    assert result.card == second_card
    assert result.rule == large


def test_pick_rule_in_memory_duplicate_resolves_to_lowest_pk() -> None:
    """Projected (unsaved) rules can collide after Feb-29 date mapping — no DB
    constraint applies to them; the lowest pk wins deterministically."""
    card = RateCard(id=1, name="Default", sort_order=0)
    first = RateRule(
        id=11,
        card_id=1,
        date_from=date(2027, 6, 1),
        date_to=date(2027, 6, 15),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    second = RateRule(
        id=12,
        card_id=1,
        date_from=date(2027, 6, 10),
        date_to=date(2027, 6, 20),
        min_party=1,
        max_party=8,
        nightly=Decimal("300.00"),
    )

    result = pick_rule_for_night(
        [card],
        {card.pk: [second, first]},
        night=date(2027, 6, 12),
        party=4,
    )

    assert isinstance(result, Picked)
    assert result.rule == first
