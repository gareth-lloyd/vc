"""Date-axis segmentation — group a card's flat RateBands into disjoint periods.

BUG-014: legacy modelled rates as a two-level hierarchy (a date *period* owning
its *occupancy bands*), so every band in a period shares that period's dates by
construction. The rebuild flattened both levels into one ``RateBand`` carrying
its own ``date_from/date_to`` alongside ``min_party/max_party``, which permits
*ragged* bands — different date spans per party band on one card, a shape legacy
could never express.

This module is the pure heart of the fix: given the inclusive ``[date_from,
date_to]`` spans of a single card's rules, it computes the minimal set of
disjoint date **segments** (future ``RatePeriod`` rows) such that every rule maps
cleanly onto a whole number of segments. Non-ragged cards collapse to exactly one
segment holding every band; ragged cards fan out, and the offending rules are
reported. Parity holds by construction: the union of segment dates equals the
union of rule dates (no night added or dropped), and each rule attaches to
exactly the segments it originally covered.

Kept free of Django/model imports (pure logic on any object exposing
``date_from``, ``date_to``, ``min_party``, ``max_party``, plus the stdlib-only
``pricing.services.intervals`` algebra) so it is shared by both the Django
data-migration backfill and the ``data_migration`` loader, and is trivially
unit-testable.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import pairwise
from typing import Any, Protocol

from pricing.services.intervals import intervals_overlap

_ONE_DAY = timedelta(days=1)


class _RuleLike(Protocol):
    # Read-only members: the utility only reads these, so both frozen value
    # objects and mutable model instances satisfy the contract.
    @property
    def date_from(self) -> date: ...
    @property
    def date_to(self) -> date: ...
    @property
    def min_party(self) -> int: ...
    @property
    def max_party(self) -> int: ...


@dataclass(frozen=True)
class Segment:
    """A disjoint date span (a future ``RatePeriod``) and the rules covering it.

    ``date_from``/``date_to`` are **inclusive** (``date_from == date_to`` is a
    legitimate single-day period). ``rules`` preserves input order.
    """

    date_from: date
    date_to: date
    rules: tuple[Any, ...]


@dataclass(frozen=True)
class RaggedRule:
    """A source rule that had to be split across more than one segment."""

    rule: Any
    segment_count: int


@dataclass(frozen=True)
class PartyCollision:
    """Two rules with overlapping party brackets share a segment (should not happen)."""

    segment: Segment
    rule_a: Any
    rule_b: Any


@dataclass(frozen=True)
class SegmentationResult:
    segments: list[Segment] = field(default_factory=list)
    ragged_rules: list[RaggedRule] = field(default_factory=list)
    anomalies: list[PartyCollision] = field(default_factory=list)
    #: Rules with a degenerate span (``date_from > date_to``). Kept out of the
    #: segmentation entirely — a bad legacy row must neither vanish silently nor
    #: fragment its (valid) siblings — and surfaced here for the caller to
    #: quarantine or hand-fix.
    invalid_spans: list[Any] = field(default_factory=list)

    @property
    def is_ragged(self) -> bool:
        return bool(self.ragged_rules)


def _covers(rule: _RuleLike, seg_from: date, seg_to: date) -> bool:
    """Whether ``rule`` spans the whole (atomic) segment ``[seg_from, seg_to]``."""
    return rule.date_from <= seg_from and seg_to <= rule.date_to


def segment_card_rules(rules: Iterable[_RuleLike]) -> SegmentationResult:
    """Segment one card's flat rules into disjoint inclusive-date periods.

    Breakpoints are taken in half-open space (``date_to + 1 day``) so abutting
    and single-day spans fall out naturally, then converted back to inclusive.
    Consecutive breakpoints bound an *atomic* segment that every rule either
    fully covers or does not touch. Segments with no covering rule (gaps between
    periods) are dropped. A rule covering more than one segment is *fragmented*,
    which is exactly the signature of a ragged card.

    Rules with a degenerate span (``date_from > date_to``) are excluded up front
    into ``invalid_spans``: they cover no segment, and leaving their breakpoints
    in would spuriously fragment their valid siblings.
    """
    all_rules = list(rules)
    valid = [r for r in all_rules if r.date_from <= r.date_to]
    invalid_spans = [r for r in all_rules if r.date_from > r.date_to]
    if not valid:
        return SegmentationResult(invalid_spans=invalid_spans)

    breakpoints: set[date] = set()
    for rule in valid:
        breakpoints.add(rule.date_from)
        breakpoints.add(rule.date_to + _ONE_DAY)
    ordered = sorted(breakpoints)

    segments: list[Segment] = []
    for lo, hi in pairwise(ordered):
        seg_from = lo
        seg_to = hi - _ONE_DAY
        covering = tuple(r for r in valid if _covers(r, seg_from, seg_to))
        if not covering:
            continue  # uncovered gap between two periods
        segments.append(Segment(date_from=seg_from, date_to=seg_to, rules=covering))

    # A rule fragmented across >1 segment marks the card ragged. Count by identity
    # so unhashable / equal rule objects are still distinguished.
    counts: dict[int, int] = {}
    for seg in segments:
        for rule in seg.rules:
            counts[id(rule)] = counts.get(id(rule), 0) + 1
    ragged_rules = [
        RaggedRule(rule=rule, segment_count=counts[id(rule)])
        for rule in valid
        if counts.get(id(rule), 0) > 1
    ]

    # Party-bracket collisions "can't happen" under the DB overlap EXCLUDE, but
    # report defensively — once per colliding pair, not once per shared segment.
    anomalies: list[PartyCollision] = []
    seen_pairs: set[frozenset[int]] = set()
    for seg in segments:
        members = seg.rules
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                if intervals_overlap((a.min_party, a.max_party), (b.min_party, b.max_party)):
                    pair = frozenset((id(a), id(b)))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    anomalies.append(PartyCollision(segment=seg, rule_a=a, rule_b=b))

    return SegmentationResult(
        segments=segments,
        ragged_rules=ragged_rules,
        anomalies=anomalies,
        invalid_spans=invalid_spans,
    )
