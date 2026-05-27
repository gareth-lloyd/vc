from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from core.exceptions import NoRateAvailable
from pricing.models import RateCard, RateRule


def nights(date_from: date, date_to: date) -> list[date]:
    """Inclusive-exclusive nights: [date_from, date_to) — date_to is checkout."""
    if date_to <= date_from:
        return []
    out: list[date] = []
    cursor = date_from
    while cursor < date_to:
        out.append(cursor)
        cursor += timedelta(days=1)
    return out


def rule_nightly(rule: RateRule) -> Decimal:
    """Return the effective nightly rate for a rule, deriving from weekly if needed."""
    if rule.nightly is not None:
        return Decimal(rule.nightly)
    if rule.weekly is not None:
        return (Decimal(rule.weekly) / Decimal(7)).quantize(Decimal("0.01"))
    raise NoRateAvailable(f"RateRule {rule.pk} is POA and cannot be priced")


def rule_specificity(rule: RateRule) -> int:
    """Days in `rule`'s date range — narrower wins on priority ties."""
    return (rule.date_to - rule.date_from).days


def any_rule_covers_night(
    cards: list[RateCard],
    rules_by_card: dict[int, list[RateRule]],
    night: date,
) -> bool:
    """True iff any rule on any of these cards covers `night`, ignoring party.

    Used by the engine to disambiguate "no rate" (no rule covers the night)
    from "party out of range" (rules cover the night, but none match the
    requested party size) — see `09-departures.md` bug #2.
    """
    for card in cards:
        for rule in rules_by_card.get(card.pk, []):
            if rule.date_from <= night <= rule.date_to:
                return True
    return False


def pick_rule_for_night(
    cards: list[RateCard],
    rules_by_card: dict[int, list[RateRule]],
    night: date,
    party: int,
) -> tuple[RateCard, RateRule] | None:
    """Pick the highest-priority rule covering `night` and `party` across cards.

    Tie-break order (per 04-pricing.md §Services step 2):
    1. Higher `priority` wins.
    2. Narrower date range wins (most-specific match).
    3. Lower `card.sort_order` wins (cross-card tie-break).
    4. Higher `rule.id` wins (deterministic fallback).
    """
    best: tuple[RateCard, RateRule] | None = None
    best_key: tuple[int, int, int, int] | None = None
    for card in cards:
        for rule in rules_by_card.get(card.pk, []):
            if not (rule.date_from <= night <= rule.date_to):
                continue
            if not (rule.min_party <= party <= rule.max_party):
                continue
            key = (
                int(rule.priority),
                -rule_specificity(rule),
                -int(card.sort_order),
                int(rule.pk),
            )
            if best_key is None or key > best_key:
                best_key = key
                best = (card, rule)
    return best
