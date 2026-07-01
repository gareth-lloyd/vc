from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from core.exceptions import NoRateAvailable
from pricing.models import RateBand, RatePeriod


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


def rule_nightly(rule: RateBand) -> Decimal:
    """Return the effective nightly rate for a rule, deriving from weekly if needed."""
    if rule.nightly is not None:
        return Decimal(rule.nightly)
    if rule.weekly is not None:
        return (Decimal(rule.weekly) / Decimal(7)).quantize(Decimal("0.01"))
    raise NoRateAvailable(f"RateBand {rule.pk} is POA and cannot be priced")


@dataclass(frozen=True)
class Picked:
    """A band (rule) was found that covers both the night and the party."""

    period: RatePeriod
    rule: RateBand


@dataclass(frozen=True)
class OutOfRange:
    """Bands cover the night but no band's party bracket includes `party`.

    Caller should raise `PartyOutOfRange` — see `09-departures.md` bug #2.
    """


@dataclass(frozen=True)
class NoCoverage:
    """No period covers the night, or a covering period carries no band.

    Caller should raise `NoRateAvailable`.
    """


PickResult = Picked | OutOfRange | NoCoverage


def pick_band_for_night(
    periods: list[RatePeriod],
    bands_by_period: dict[int, list[RateBand]],
    night: date,
    party: int,
) -> PickResult:
    """Pick the band covering `night` and `party`, with its owning period.

    Periods are the disjoint date axis (GAP-056): the target model guarantees at
    most one active period covers any night, so for real data this simply finds
    the covering period's matching band. The **lowest-pk matching band across all
    covering periods wins** — the deterministic tie-break for the two transitional
    cases where periods can still overlap: expand-phase data carrying leftover
    card-precedence overlaps (pre Unit-9 EXCLUDE), and in-memory projected periods
    that collide after Feb-29 date mapping. Lowest-pk mirrors the carry-forward
    materialiser's trim (which lets the lower-pk band claim the shared night
    first), so a projected quote and its materialised twin price identically.

    Returns a tagged result so the caller can distinguish "no band at all"
    (`NoCoverage`) from "a period covers the night but the party is outside
    every band" (`OutOfRange`). The coverage flag spans *all* covering periods:
    a band whose bracket excludes the request must neither shadow a matching
    band on another covering period nor erase the OutOfRange signal.
    """
    any_band_covered = False
    best_rule: RateBand | None = None
    best_period: RatePeriod | None = None

    for period in periods:
        if not (period.date_from <= night <= period.date_to):
            continue
        for rule in bands_by_period.get(period.pk, []):
            # The night is covered by *some* band (bands inherit the period's
            # dates) — even if the party bracket excludes it. Remember this so
            # we distinguish "out of range" from "no coverage" without a
            # second pass.
            any_band_covered = True
            if not (rule.min_party <= party <= rule.max_party):
                continue
            if best_rule is None or int(rule.pk) < int(best_rule.pk):
                best_rule = rule
                best_period = period

    if best_rule is not None:
        assert best_period is not None  # set in lockstep with best_rule
        return Picked(period=best_period, rule=best_rule)
    if any_band_covered:
        return OutOfRange()
    return NoCoverage()
