"""BUG-016 Unit 1 — the one shared inclusive-interval algebra.

`intervals_overlap` / `subtract_intervals` pin the semantics every rate-grid
producer relies on: inclusive ``(low, high)`` brackets, ``high=None`` meaning
unbounded above, subtraction splitting interior overlaps and returning
remainders ascending by low.
"""

from pricing.services.intervals import intervals_overlap, subtract_intervals


class TestIntervalsOverlap:
    def test_disjoint(self) -> None:
        assert not intervals_overlap((1, 4), (5, 8))
        assert not intervals_overlap((5, 8), (1, 4))

    def test_touching_endpoint_is_overlap(self) -> None:
        assert intervals_overlap((1, 4), (4, 8))

    def test_nested(self) -> None:
        assert intervals_overlap((1, 10), (3, 5))

    def test_unbounded_right_side(self) -> None:
        assert intervals_overlap((1, None), (100, 200))
        assert intervals_overlap((100, 200), (1, None))

    def test_unbounded_still_disjoint_below(self) -> None:
        assert not intervals_overlap((5, None), (1, 4))
        assert not intervals_overlap((1, 4), (5, None))

    def test_both_unbounded(self) -> None:
        assert intervals_overlap((1, None), (9, None))


class TestSubtractIntervals:
    def test_no_overlap_unchanged(self) -> None:
        assert subtract_intervals([(1, 4)], [(6, 8)]) == [(1, 4)]

    def test_fully_covered_empties(self) -> None:
        assert subtract_intervals([(3, 5)], [(1, 8)]) == []

    def test_interior_subtrahend_splits(self) -> None:
        assert subtract_intervals([(1, 10)], [(4, 6)]) == [(1, 3), (7, 10)]

    def test_clip_left(self) -> None:
        assert subtract_intervals([(1, 10)], [(1, 3)]) == [(4, 10)]

    def test_clip_right(self) -> None:
        assert subtract_intervals([(1, 10)], [(8, 10)]) == [(1, 7)]

    def test_unbounded_minuend_keeps_open_top(self) -> None:
        assert subtract_intervals([(1, None)], [(4, 6)]) == [(1, 3), (7, None)]

    def test_unbounded_subtrahend_clips_top(self) -> None:
        assert subtract_intervals([(1, 10)], [(5, None)]) == [(1, 4)]

    def test_unbounded_subtrahend_over_unbounded_minuend(self) -> None:
        assert subtract_intervals([(1, None)], [(5, None)]) == [(1, 4)]

    def test_multiple_subtrahends_apply_in_sequence(self) -> None:
        assert subtract_intervals([(1, None)], [(2, 3), (6, 7)]) == [
            (1, 1),
            (4, 5),
            (8, None),
        ]

    def test_multiple_minuends(self) -> None:
        assert subtract_intervals([(1, 3), (7, 9)], [(2, 8)]) == [(1, 1), (9, 9)]

    def test_result_ascending(self) -> None:
        out = subtract_intervals([(7, 9), (1, 3)], [(5, 5)])
        assert out == sorted(out, key=lambda iv: iv[0])

    def test_empty_subtrahends_returns_sorted_copy(self) -> None:
        assert subtract_intervals([(7, 9), (1, 3)], []) == [(1, 3), (7, 9)]

    def test_single_point_remainder_kept(self) -> None:
        assert subtract_intervals([(1, 2)], [(2, 8)]) == [(1, 1)]
