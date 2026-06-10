from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class Picked:
    """A rule was found that covers both the night and the party."""

    card: RateCard
    rule: RateRule


@dataclass(frozen=True)
class OutOfRange:
    """Rules cover the night but no rule's party bracket includes `party`.

    Caller should raise `PartyOutOfRange` — see `09-departures.md` bug #2.
    """


@dataclass(frozen=True)
class NoCoverage:
    """No rule on any of the supplied cards covers the night at all.

    Caller should raise `NoRateAvailable`.
    """


PickResult = Picked | OutOfRange | NoCoverage


def pick_rule_for_night(
    cards: list[RateCard],
    rules_by_card: dict[int, list[RateRule]],
    night: date,
    party: int,
) -> PickResult:
    """Pick the rule covering `night` and `party` by card order.

    Cards are walked in the caller-supplied order — both the engine and the
    projection load them `("sort_order", "pk")` — and the first card with a
    rule covering both the night and the party wins; later cards never
    override it, however narrow their rules. Within a card the DB forbids
    overlapping rules outright (`raterule_no_overlap`), but in-memory
    projected rules can collide after Feb-29 date mapping; the lowest pk
    wins deterministically.

    Returns a tagged result so the caller can distinguish "no rule at all"
    (`NoCoverage`) from "rules cover the night but the party is outside
    every bracket" (`OutOfRange`). The night-coverage flag spans *all*
    cards: a first-card rule whose party bracket excludes the request must
    neither shadow a matching rule on a later card nor erase the
    OutOfRange signal.
    """
    any_rule_covered = False

    for card in cards:
        best: RateRule | None = None
        for rule in rules_by_card.get(card.pk, []):
            if not (rule.date_from <= night <= rule.date_to):
                continue
            # The night is covered by *some* rule — even if the party
            # bracket excludes it. Remember this so we can distinguish
            # "out of range" from "no coverage" without a second pass.
            any_rule_covered = True
            if not (rule.min_party <= party <= rule.max_party):
                continue
            if best is None or int(rule.pk) < int(best.pk):
                best = rule
        if best is not None:
            return Picked(card=card, rule=best)

    if any_rule_covered:
        return OutOfRange()
    return NoCoverage()
