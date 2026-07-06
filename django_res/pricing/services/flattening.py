"""The one canonical rate-grid flattener (BUG-016).

"Flatten the rate grid to (date x party)-disjoint bands, precedence wins,
namespace collision fragments" was reimplemented by four producers (projection,
carryover, the legacy loader, the period backfill) that were contracted to
agree but didn't — a projected quote could price differently from the
materialised rows it promised. This module is the single implementation they
all consume.

Contract (the property the tests prove pointwise): for every (night, party)
point, the flat cell's source is exactly the band ``pick_band_for_night``
would pick over the raw inputs — the source with the lowest ``precedence``
key whose date span and party bracket cover the point. Consequences:

* an interior date collision keeps **both** sides of the loser (split, not
  clip), including single-day remainders;
* a party collision keeps every uncovered bracket of the loser (a bracket
  split yields two fragments);
* a source only lands in ``dropped_sources`` when it wins no cell at all.

Fragmenting is namespaced per source: ``fragment_index`` counts a source's
surviving cells in ``(period date_from, min_party)`` order, 0-based — index 0
keeps the source's bare identity, index n >= 1 is rendered ``#seg{n}`` by
consumers that persist ids. The result is input-order-independent; equal
``precedence`` keys are a caller bug and raise ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from pricing.services.intervals import Interval, subtract_intervals
from pricing.services.segmentation import segment_card_rules

_ONE_DAY = timedelta(days=1)

# One resolved cell of an atomic segment: (min_party, max_party, source).
type _Cell[P] = tuple[int, int, SourceBand[P]]


# eq=False: a SourceBand's identity IS its (unique) precedence key, and
# identity semantics keep instances hashable even with dict payloads —
# field-wise eq/hash would crash the natural `set(result.dropped_sources)`.
@dataclass(frozen=True, eq=False)
class SourceBand[P]:
    """One raw input band: an inclusive date span x inclusive party bracket.

    ``precedence`` is an opaque, totally-ordered tuple — lowest wins a
    contested cell — and must be unique per source (it is also the source's
    identity in the result). ``payload`` is carried through untouched (prices,
    notes, source-row references — whatever the producer needs back).
    """

    date_from: date
    date_to: date
    min_party: int
    max_party: int
    precedence: tuple[Any, ...]
    payload: P


@dataclass(frozen=True)
class FlatBand[P]:
    """A surviving (party bracket, source) cell of one flat period."""

    min_party: int
    max_party: int
    source: SourceBand[P]
    fragment_index: int


@dataclass(frozen=True)
class FlatPeriod[P]:
    """A maximal date span with one unchanging set of resolved bands.

    ``bands`` is precedence-ordered — ``bands[0]`` is the span's winner —
    with a party-split source's fragments adjacent in ascending bracket order.
    """

    date_from: date
    date_to: date
    bands: tuple[FlatBand[P], ...]


@dataclass(frozen=True)
class FlatteningResult[P]:
    """The disjoint grid plus what the flattening did to the inputs.

    ``dropped_sources`` won no cell (fully shadowed); ``invalid_spans`` had a
    degenerate span on either axis (``date_from > date_to`` or ``min_party >
    max_party``) and were quarantined up front (a bad row must neither vanish
    silently, fragment its valid siblings, nor — for an inverted bracket —
    poison the interval subtraction); ``party_clipped`` survived but lost part
    of their party bracket to a higher-precedence source on shared dates. All
    three are precedence-ordered.
    """

    periods: list[FlatPeriod[P]]
    dropped_sources: list[SourceBand[P]]
    invalid_spans: list[SourceBand[P]]
    party_clipped: list[SourceBand[P]]


def flatten_rate_grid[P](sources: Iterable[SourceBand[P]]) -> FlatteningResult[P]:
    """Flatten possibly-overlapping source bands into the disjoint grid."""
    source_list = list(sources)
    seen: set[tuple[Any, ...]] = set()
    for source in source_list:
        if source.precedence in seen:
            raise ValueError(f"duplicate precedence key {source.precedence!r} in flatten inputs")
        seen.add(source.precedence)

    # Quarantine party-inverted brackets before segmentation, symmetric with
    # segment_card_rules' own date-inverted quarantine: a (5, 3) bracket fed
    # into subtract_intervals would yield overlapping remainders and break the
    # grid's disjointness.
    party_invalid = [s for s in source_list if s.min_party > s.max_party]
    # segment_card_rules' ragged_rules/anomalies diagnostics are deliberately
    # discarded: they describe *persisted* grids (where party collisions can't
    # happen under the DB EXCLUDEs), while this flattener feeds it
    # party-overlapping bands by design and resolves them by precedence below.
    segmentation = segment_card_rules([s for s in source_list if s.min_party <= s.max_party])

    # Resolve each atomic date segment: precedence order, party-interval
    # subtraction — the winner keeps every cell, later sources the remainder.
    resolved: list[tuple[date, date, list[_Cell[P]]]] = []
    clipped_keys: set[tuple[Any, ...]] = set()
    for segment in segmentation.segments:
        cells: list[_Cell[P]] = []
        claimed: list[Interval] = []
        for source in sorted(segment.rules, key=lambda s: s.precedence):
            bracket: Interval = (source.min_party, source.max_party)
            remainders = subtract_intervals([bracket], claimed)
            if remainders and remainders != [bracket]:
                clipped_keys.add(source.precedence)
            for lo, hi in remainders:
                assert hi is not None  # inputs are bounded, so remainders are
                cells.append((lo, hi, source))
                claimed.append((lo, hi))
        resolved.append((segment.date_from, segment.date_to, cells))

    # Coalesce date-adjacent segments whose resolved cells are identical —
    # undoing the spurious breakpoints left by fully-shadowed sources so a
    # non-ragged grid round-trips to the same period shape it came in with.
    coalesced: list[tuple[date, date, list[_Cell[P]]]] = []
    prev_signature: list[tuple[tuple[Any, ...], int, int]] | None = None
    for seg_from, seg_to, cells in resolved:  # segments arrive in date order
        signature = [(s.precedence, lo, hi) for lo, hi, s in cells]
        if coalesced:
            prev_from, prev_to, prev_cells = coalesced[-1]
            if prev_to + _ONE_DAY == seg_from and prev_signature == signature:
                coalesced[-1] = (prev_from, seg_to, prev_cells)
                continue
        coalesced.append((seg_from, seg_to, cells))
        prev_signature = signature

    # Fragment indices: count each source's surviving cells in
    # (period date_from, min_party) order — the order they occur below,
    # since periods are date-ordered and a source's cells within one period
    # come back ascending from subtract_intervals.
    fragment_counts: dict[tuple[Any, ...], int] = {}
    periods: list[FlatPeriod[P]] = []
    for seg_from, seg_to, cells in coalesced:
        bands: list[FlatBand[P]] = []
        for lo, hi, source in cells:
            index = fragment_counts.get(source.precedence, 0)
            fragment_counts[source.precedence] = index + 1
            bands.append(FlatBand(min_party=lo, max_party=hi, source=source, fragment_index=index))
        periods.append(FlatPeriod(date_from=seg_from, date_to=seg_to, bands=tuple(bands)))

    invalid = sorted([*segmentation.invalid_spans, *party_invalid], key=lambda s: s.precedence)
    invalid_keys = {source.precedence for source in invalid}
    dropped = sorted(
        (
            source
            for source in source_list
            if source.precedence not in fragment_counts and source.precedence not in invalid_keys
        ),
        key=lambda s: s.precedence,
    )
    clipped = sorted(
        (source for source in source_list if source.precedence in clipped_keys),
        key=lambda s: s.precedence,
    )
    return FlatteningResult(
        periods=periods,
        dropped_sources=dropped,
        invalid_spans=invalid,
        party_clipped=clipped,
    )
