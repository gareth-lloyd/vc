"""Inclusive integer-interval algebra shared by every rate-grid producer.

BUG-016: the party-bracket overlap predicate was hand-rolled three times
(legacy loader resolver, carryover, segmentation) and the bracket subtraction
twice. This module is the single implementation. The loader resolver and
segmentation consume it today; the remaining BUG-016 units move carryover and
the new grid flattener onto it too.

An interval is an inclusive ``(low, high)`` bracket over integers, with
``high=None`` meaning unbounded above (e.g. "party up to property capacity,
capacity unknown here"). ``low`` is always concrete.
"""

from __future__ import annotations

Interval = tuple[int, int | None]


def intervals_overlap(a: Interval, b: Interval) -> bool:
    """Whether two inclusive brackets share at least one integer."""
    return (a[1] is None or b[0] <= a[1]) and (b[1] is None or a[0] <= b[1])


def subtract_intervals(intervals: list[Interval], subtrahends: list[Interval]) -> list[Interval]:
    """Remainders of ``intervals`` minus every subtrahend, ascending by low.

    Each subtrahend is removed from every surviving piece in turn; an interior
    subtrahend splits a piece into two. The result is disjoint whenever the
    inputs within ``intervals`` are.
    """
    remaining = list(intervals)
    for slo, shi in subtrahends:
        survivors: list[Interval] = []
        for lo, hi in remaining:
            if not intervals_overlap((lo, hi), (slo, shi)):
                survivors.append((lo, hi))
                continue
            if lo < slo:
                survivors.append((lo, slo - 1))
            if shi is not None and (hi is None or shi < hi):
                survivors.append((shi + 1, hi))
        remaining = survivors
    return sorted(remaining, key=lambda iv: iv[0])
