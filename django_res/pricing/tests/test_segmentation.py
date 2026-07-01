"""Unit 1 — pure date-axis segmentation of a card's flat RateBands.

These tests use lightweight fake rules (no DB) so the utility stays a pure
function: given the inclusive `[date_from, date_to]` spans of a card's rules,
it produces the disjoint period segments each rule maps onto, flags cards
whose rules got fragmented (ragged), and reports party-bracket collisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from pricing.services.segmentation import segment_card_rules


@dataclass(frozen=True)
class _Rule:
    """Minimal stand-in for a RateBand row: an inclusive span + party bracket."""

    label: str
    date_from: date
    date_to: date
    min_party: int = 1
    max_party: int = 10


def d(month: int, day: int) -> date:
    return date(2026, month, day)


def _labels(rules: tuple) -> list[str]:
    return [r.label for r in rules]


def test_empty_input_yields_empty_result() -> None:
    result = segment_card_rules([])
    assert result.segments == []
    assert result.is_ragged is False
    assert result.ragged_rules == []
    assert result.anomalies == []


def test_single_rule_is_one_period_not_ragged() -> None:
    a = _Rule("A", d(6, 1), d(6, 30))
    result = segment_card_rules([a])

    assert len(result.segments) == 1
    seg = result.segments[0]
    assert (seg.date_from, seg.date_to) == (d(6, 1), d(6, 30))
    assert _labels(seg.rules) == ["A"]
    assert result.is_ragged is False


def test_sibling_bands_sharing_dates_collapse_to_one_period() -> None:
    # The common non-ragged case: two occupancy bands, identical dates.
    a = _Rule("A", d(6, 1), d(6, 30), min_party=2, max_party=4)
    b = _Rule("B", d(6, 1), d(6, 30), min_party=5, max_party=6)
    result = segment_card_rules([a, b])

    assert len(result.segments) == 1
    seg = result.segments[0]
    assert (seg.date_from, seg.date_to) == (d(6, 1), d(6, 30))
    assert _labels(seg.rules) == ["A", "B"]
    assert result.is_ragged is False
    assert result.anomalies == []


def test_two_adjacent_clean_periods_are_two_segments_not_ragged() -> None:
    a = _Rule("A", d(6, 1), d(6, 15))
    b = _Rule("B", d(6, 16), d(6, 30))
    result = segment_card_rules([a, b])

    assert [(s.date_from, s.date_to) for s in result.segments] == [
        (d(6, 1), d(6, 15)),
        (d(6, 16), d(6, 30)),
    ]
    assert [_labels(s.rules) for s in result.segments] == [["A"], ["B"]]
    # Neither rule was fragmented — distinct periods, not raggedness.
    assert result.is_ragged is False


def test_gap_between_periods_is_dropped() -> None:
    a = _Rule("A", d(6, 1), d(6, 10))
    b = _Rule("B", d(6, 20), d(6, 30))
    result = segment_card_rules([a, b])

    # The uncovered Jun 11-19 stretch produces no phantom segment.
    assert [(s.date_from, s.date_to) for s in result.segments] == [
        (d(6, 1), d(6, 10)),
        (d(6, 20), d(6, 30)),
    ]
    assert result.is_ragged is False


def test_ragged_shared_boundary_day_becomes_single_day_period() -> None:
    # Legacy-impossible ragged shape: bands abut on a shared boundary day.
    a = _Rule("A", d(6, 1), d(6, 28), min_party=2, max_party=4)
    b = _Rule("B", d(6, 28), d(8, 2), min_party=5, max_party=6)
    result = segment_card_rules([a, b])

    spans = [(s.date_from, s.date_to) for s in result.segments]
    assert spans == [
        (d(6, 1), d(6, 27)),
        (d(6, 28), d(6, 28)),  # single-day period carrying BOTH bands
        (d(6, 29), d(8, 2)),
    ]
    assert [_labels(s.rules) for s in result.segments] == [["A"], ["A", "B"], ["B"]]

    assert result.is_ragged is True
    # Both rules were fragmented across >1 segment.
    fragmented = {r.rule.label: r.segment_count for r in result.ragged_rules}
    assert fragmented == {"A": 2, "B": 2}
    # Party brackets don't overlap on the shared day — no anomaly.
    assert result.anomalies == []


def test_overlapping_party_on_a_segment_is_reported_as_anomaly() -> None:
    # Defensive: a DB satisfying raterule_no_overlap can't produce this, but
    # the utility must flag it rather than silently emit an invalid period.
    a = _Rule("A", d(6, 1), d(6, 30), min_party=2, max_party=5)
    b = _Rule("B", d(6, 1), d(6, 30), min_party=4, max_party=6)
    result = segment_card_rules([a, b])

    assert len(result.anomalies) == 1
    collision = result.anomalies[0]
    assert {collision.rule_a.label, collision.rule_b.label} == {"A", "B"}
    assert (collision.segment.date_from, collision.segment.date_to) == (d(6, 1), d(6, 30))


def test_segments_are_chronological_regardless_of_input_order() -> None:
    later = _Rule("later", d(7, 1), d(7, 31))
    earlier = _Rule("earlier", d(6, 1), d(6, 30))
    result = segment_card_rules([later, earlier])

    assert [s.date_from for s in result.segments] == [d(6, 1), d(7, 1)]


def test_nested_rule_makes_card_ragged() -> None:
    # A band wholly inside another: legacy-impossible, so the card is ragged.
    # The OUTER rule genuinely fragments into three bands across three periods.
    outer = _Rule("outer", d(6, 1), d(6, 30), min_party=2, max_party=4)
    inner = _Rule("inner", d(6, 10), d(6, 20), min_party=5, max_party=6)
    result = segment_card_rules([outer, inner])

    assert [_labels(s.rules) for s in result.segments] == [
        ["outer"],
        ["outer", "inner"],
        ["outer"],
    ]
    assert result.is_ragged is True
    fragmented = {r.rule.label: r.segment_count for r in result.ragged_rules}
    assert fragmented == {"outer": 3}
    assert result.anomalies == []


def test_inverted_span_is_quarantined_not_dropped_and_spares_siblings() -> None:
    # A garbage legacy row (date_from > date_to) must not vanish silently, and
    # must NOT fragment its clean sibling into false raggedness.
    good = _Rule("good", d(6, 1), d(6, 30))
    inverted = _Rule("inverted", d(6, 20), d(6, 10))
    result = segment_card_rules([good, inverted])

    assert [(s.date_from, s.date_to) for s in result.segments] == [(d(6, 1), d(6, 30))]
    assert [_labels(s.rules) for s in result.segments] == [["good"]]
    assert result.is_ragged is False
    assert _labels(tuple(result.invalid_spans)) == ["inverted"]


def test_only_invalid_spans_yields_no_segments_but_reports_them() -> None:
    inverted = _Rule("inverted", d(6, 20), d(6, 10))
    result = segment_card_rules([inverted])

    assert result.segments == []
    assert result.is_ragged is False
    assert _labels(tuple(result.invalid_spans)) == ["inverted"]


def test_party_collision_reported_once_across_multiple_segments() -> None:
    # A and B overlap on party AND share dates; C forces extra breakpoints so the
    # A/B pair co-occurs in three atomic segments — still one anomaly, not three.
    a = _Rule("A", d(6, 1), d(6, 30), min_party=2, max_party=5)
    b = _Rule("B", d(6, 1), d(6, 30), min_party=4, max_party=6)
    c = _Rule("C", d(6, 10), d(6, 20), min_party=7, max_party=8)
    result = segment_card_rules([a, b, c])

    assert len(result.anomalies) == 1
    collision = result.anomalies[0]
    assert {collision.rule_a.label, collision.rule_b.label} == {"A", "B"}
