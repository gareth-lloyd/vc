"""Unit tests for the pure date logic in `seeding/_pricing_helpers.py`.

`_season_segments` partitions a plan window into maximal same-season runs.
The RateRule rows it ultimately feeds carry a strict
`raterule_date_from_lt_date_to` CHECK, so a segment must never be zero-width
(`from == to`) — otherwise seeding blows up on a month-end window start (e.g.
the alt-currency plan dated one day before a June-1 primary lands on May 31, a
1-day Mid sliver before the June Peak run).
"""

from __future__ import annotations

from datetime import date, timedelta

from seeding._pricing_helpers import _season_segments


def _assert_gapfree_and_positive(
    segments: list[tuple[date, date, int]], window_from: date, window_to: date
) -> None:
    assert segments, "segments must cover the window"
    assert segments[0][0] == window_from
    assert segments[-1][1] == window_to
    prev_to = None
    for seg_from, seg_to, _season in segments:
        assert seg_from < seg_to, f"zero-width / inverted segment {seg_from}..{seg_to}"
        if prev_to is not None:
            assert seg_from == prev_to + timedelta(days=1), "segments must be gap-free"
        prev_to = seg_to


def test_month_end_start_does_not_emit_zero_width_segment() -> None:
    # May 31 (Mid) rolls into June 1 (Peak): the naive split leaves a 1-day
    # May 31..May 31 segment, which violates the strict RateRule date check.
    window_from, window_to = date(2026, 5, 31), date(2027, 7, 5)
    segments = _season_segments(window_from, window_to)
    _assert_gapfree_and_positive(segments, window_from, window_to)


def test_regular_month_start_segments_stay_gapfree() -> None:
    window_from, window_to = date(2026, 6, 1), date(2027, 8, 5)
    segments = _season_segments(window_from, window_to)
    _assert_gapfree_and_positive(segments, window_from, window_to)
