"""BUG-016 Unit 2 — the one canonical rate-grid flattener.

`flatten_rate_grid` turns possibly-overlapping source bands into a
(date x party)-disjoint grid. Its contract: for every (night, party) point,
the flat cell's source is exactly the band `pick_band_for_night` would pick
over the raw inputs (lowest precedence key covering the point) — proven
pointwise by `TestPointwiseEquivalence` against the real picker.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pytest

from pricing.models import RateBand, RatePeriod
from pricing.services.flattening import FlatteningResult, SourceBand, flatten_rate_grid
from pricing.services.rates import Picked, pick_band_for_night

D = date  # brevity in case tables


def src(
    pk: int,
    date_from: date,
    date_to: date,
    min_party: int = 1,
    max_party: int = 8,
    payload: object = None,
) -> SourceBand:
    """A SourceBand whose precedence key doubles as its oracle pk."""
    return SourceBand(
        date_from=date_from,
        date_to=date_to,
        min_party=min_party,
        max_party=max_party,
        precedence=(pk,),
        payload=payload if payload is not None else {"pk": pk},
    )


def _shape(result: FlatteningResult) -> list[object]:
    """A comparable snapshot of the resolved grid (sources by identity)."""
    return [
        (
            p.date_from,
            p.date_to,
            [(b.source, b.min_party, b.max_party, b.fragment_index) for b in p.bands],
        )
        for p in result.periods
    ]


class TestFlattenRateGrid:
    def test_single_source_single_period(self) -> None:
        a = src(1, D(2026, 6, 1), D(2026, 6, 30))
        result = flatten_rate_grid([a])
        assert len(result.periods) == 1
        period = result.periods[0]
        assert (period.date_from, period.date_to) == (D(2026, 6, 1), D(2026, 6, 30))
        assert len(period.bands) == 1
        band = period.bands[0]
        assert (band.min_party, band.max_party) == (1, 8)
        assert band.source is a
        assert band.fragment_index == 0
        assert result.dropped_sources == []
        assert result.invalid_spans == []
        assert result.party_clipped == []

    def test_non_ragged_disjoint_parties_share_one_period(self) -> None:
        a = src(2, D(2026, 6, 1), D(2026, 6, 30), 1, 4)
        b = src(1, D(2026, 6, 1), D(2026, 6, 30), 5, 8)
        result = flatten_rate_grid([a, b])
        assert len(result.periods) == 1
        period = result.periods[0]
        # Precedence order: b (key (1,)) before a (key (2,)).
        assert [band.source for band in period.bands] == [b, a]
        assert all(band.fragment_index == 0 for band in period.bands)

    def test_identical_spans_partial_party_overlap_clips_loser(self) -> None:
        winner = src(1, D(2026, 6, 1), D(2026, 6, 30), 1, 4)
        loser = src(2, D(2026, 6, 1), D(2026, 6, 30), 1, 8)
        result = flatten_rate_grid([winner, loser])
        assert len(result.periods) == 1
        cells = [(band.source, band.min_party, band.max_party) for band in result.periods[0].bands]
        assert cells == [(winner, 1, 4), (loser, 5, 8)]
        assert result.party_clipped == [loser]
        assert result.dropped_sources == []

    def test_party_split_yields_two_fragments(self) -> None:
        winner = src(1, D(2026, 6, 1), D(2026, 6, 30), 3, 5)
        loser = src(2, D(2026, 6, 1), D(2026, 6, 30), 1, 8)
        result = flatten_rate_grid([winner, loser])
        assert len(result.periods) == 1
        loser_bands = [band for band in result.periods[0].bands if band.source is loser]
        # Ordered by (date_from, min_party): (1,2) is fragment 0, (6,8) fragment 1.
        assert [(b.min_party, b.max_party, b.fragment_index) for b in loser_bands] == [
            (1, 2, 0),
            (6, 8, 1),
        ]

    def test_fully_shadowed_source_dropped(self) -> None:
        winner = src(1, D(2026, 6, 1), D(2026, 6, 30), 1, 8)
        loser = src(2, D(2026, 6, 1), D(2026, 6, 30), 2, 6)
        result = flatten_rate_grid([winner, loser])
        assert result.dropped_sources == [loser]
        assert len(result.periods) == 1
        assert [band.source for band in result.periods[0].bands] == [winner]
        # Dropped is dropped, not clipped.
        assert result.party_clipped == []

    def test_interior_date_collision_keeps_both_sides(self) -> None:
        loser = src(2, D(2026, 6, 1), D(2026, 6, 30))
        winner = src(1, D(2026, 6, 10), D(2026, 6, 20))
        result = flatten_rate_grid([loser, winner])
        spans = [(p.date_from, p.date_to, [b.source for b in p.bands]) for p in result.periods]
        assert spans == [
            (D(2026, 6, 1), D(2026, 6, 9), [loser]),
            (D(2026, 6, 10), D(2026, 6, 20), [winner]),
            (D(2026, 6, 21), D(2026, 6, 30), [loser]),
        ]
        loser_fragments = [
            (p.date_from, b.fragment_index)
            for p in result.periods
            for b in p.bands
            if b.source is loser
        ]
        assert loser_fragments == [(D(2026, 6, 1), 0), (D(2026, 6, 21), 1)]

    def test_single_day_remainder_kept(self) -> None:
        loser = src(2, D(2026, 6, 1), D(2026, 6, 2))
        winner = src(1, D(2026, 6, 2), D(2026, 6, 30))
        result = flatten_rate_grid([loser, winner])
        assert (result.periods[0].date_from, result.periods[0].date_to) == (
            D(2026, 6, 1),
            D(2026, 6, 1),
        )
        assert [band.source for band in result.periods[0].bands] == [loser]

    def test_invalid_span_quarantined_without_fragmenting_siblings(self) -> None:
        ok = src(1, D(2026, 6, 1), D(2026, 6, 30))
        bad = src(2, D(2026, 6, 20), D(2026, 6, 10))
        result = flatten_rate_grid([ok, bad])
        assert result.invalid_spans == [bad]
        assert result.dropped_sources == []
        assert len(result.periods) == 1  # bad's breakpoints must not split ok

    def test_inverted_party_bracket_quarantined(self) -> None:
        # A (5, 3) bracket fed to the subtraction would yield overlapping
        # remainders — it must be quarantined, not resolved.
        bad = src(1, D(2026, 6, 1), D(2026, 6, 30), 5, 3)
        ok = src(2, D(2026, 6, 1), D(2026, 6, 30), 1, 8)
        result = flatten_rate_grid([bad, ok])
        assert result.invalid_spans == [bad]
        assert result.party_clipped == []
        assert len(result.periods) == 1
        assert [(b.min_party, b.max_party) for b in result.periods[0].bands] == [(1, 8)]

    def test_payload_is_opaque(self) -> None:
        payload = {"is_poa": True, "weekly": None, "anything": object()}
        a = src(1, D(2026, 6, 1), D(2026, 6, 30), payload=payload)
        result = flatten_rate_grid([a])
        assert result.periods[0].bands[0].source.payload is payload
        # Identity semantics: hashable even with a dict payload, so consumers
        # can build sets of dropped/clipped sources.
        assert {a} == {result.periods[0].bands[0].source}

    def test_shadowed_interior_source_coalesces_back_to_one_period(self) -> None:
        winner = src(1, D(2026, 6, 1), D(2026, 6, 30), 1, 8)
        shadowed = src(2, D(2026, 6, 10), D(2026, 6, 20), 1, 8)
        result = flatten_rate_grid([winner, shadowed])
        # The shadowed source's breakpoints leave three atomic segments that all
        # resolve to [winner (1,8)] — they must merge back into one period.
        assert len(result.periods) == 1
        assert (result.periods[0].date_from, result.periods[0].date_to) == (
            D(2026, 6, 1),
            D(2026, 6, 30),
        )
        assert result.dropped_sources == [shadowed]

    def test_distinct_sources_do_not_coalesce(self) -> None:
        a = src(1, D(2026, 6, 1), D(2026, 6, 10))
        b = src(2, D(2026, 6, 11), D(2026, 6, 20))
        result = flatten_rate_grid([a, b])
        assert len(result.periods) == 2

    def test_input_order_independent(self) -> None:
        sources = [
            src(3, D(2026, 6, 1), D(2026, 6, 30), 1, 8),
            src(1, D(2026, 6, 10), D(2026, 6, 20), 2, 6),
            src(2, D(2026, 6, 15), D(2026, 7, 15), 1, 4),
            src(4, D(2026, 7, 1), D(2026, 7, 31), 5, 8),
        ]
        rng = random.Random(2026)
        baseline = flatten_rate_grid(sources)
        for _ in range(5):
            shuffled = sources[:]
            rng.shuffle(shuffled)
            result = flatten_rate_grid(shuffled)
            assert _shape(result) == _shape(baseline)
            assert result.dropped_sources == baseline.dropped_sources

    def test_duplicate_precedence_raises(self) -> None:
        a = src(1, D(2026, 6, 1), D(2026, 6, 30))
        b = src(1, D(2026, 7, 1), D(2026, 7, 31))
        with pytest.raises(ValueError, match="precedence"):
            flatten_rate_grid([a, b])

    def test_empty_input(self) -> None:
        result: FlatteningResult[object] = flatten_rate_grid([])
        assert result.periods == []
        assert result.dropped_sources == []


# --- Pointwise equivalence with the lazy picker (the flattener's contract) ---


GRIDS = {
    "tie_break_pk_opposes_date_order": [
        src(2, D(2026, 6, 1), D(2026, 6, 30), 1, 8),
        src(1, D(2026, 6, 1), D(2026, 6, 30), 1, 8),
    ],
    "interior_collision": [
        src(2, D(2026, 6, 1), D(2026, 6, 30), 1, 8),
        src(1, D(2026, 6, 10), D(2026, 6, 20), 1, 8),
    ],
    "party_widening_bug_case": [
        src(1, D(2026, 6, 1), D(2026, 6, 30), 1, 4),
        src(2, D(2026, 6, 1), D(2026, 6, 30), 1, 8),
    ],
    "feb29_mapped_pileup": [
        # A leap-year-mapped range landing on its neighbour (span preserved,
        # calendar lost a day) — one-day overlap at the boundary.
        src(1, D(2027, 2, 22), D(2027, 2, 28), 1, 8),
        src(2, D(2027, 2, 28), D(2027, 3, 6), 1, 8),
    ],
    "weekday_map_double_shift": [
        # Neighbours shifted toward each other by up to 3 days each.
        src(1, D(2027, 5, 1), D(2027, 5, 10), 1, 8),
        src(2, D(2027, 5, 8), D(2027, 5, 17), 1, 8),
    ],
    "ragged_party_mesh": [
        src(1, D(2026, 6, 1), D(2026, 6, 15), 3, 5),
        src(2, D(2026, 6, 10), D(2026, 6, 25), 1, 8),
        src(3, D(2026, 6, 5), D(2026, 6, 30), 2, 10),
    ],
    "gap_and_out_of_range": [
        src(1, D(2026, 6, 1), D(2026, 6, 10), 4, 6),
        src(2, D(2026, 6, 20), D(2026, 6, 30), 1, 2),
    ],
    "single_day_slivers": [
        src(1, D(2026, 6, 2), D(2026, 6, 2), 1, 8),
        src(2, D(2026, 6, 1), D(2026, 6, 3), 1, 8),
    ],
}


def _raw_context(sources: list[SourceBand]) -> tuple[list[RatePeriod], dict[int, list[RateBand]]]:
    """One in-memory period per source, band pk = the source's precedence key.

    `pick_band_for_night` tie-breaks on `int(rule.pk)`, so the harness maps the
    single-int precedence tuples of these fixtures straight onto pks.
    """
    periods: list[RatePeriod] = []
    bands_by_period: dict[int, list[RateBand]] = {}
    for i, source in enumerate(sources, start=1):
        pk = source.precedence[0]
        periods.append(RatePeriod(id=1000 + i, date_from=source.date_from, date_to=source.date_to))
        bands_by_period[1000 + i] = [
            RateBand(
                id=pk,
                period_id=1000 + i,
                min_party=source.min_party,
                max_party=source.max_party,
            )
        ]
    return periods, bands_by_period


def _flat_context(sources: list[SourceBand]) -> tuple[list[RatePeriod], dict[int, list[RateBand]]]:
    """The flattened grid as in-memory periods/bands, band pk = source key."""
    result = flatten_rate_grid(sources)
    periods: list[RatePeriod] = []
    bands_by_period: dict[int, list[RateBand]] = {}
    for i, flat_period in enumerate(result.periods, start=1):
        periods.append(
            RatePeriod(id=2000 + i, date_from=flat_period.date_from, date_to=flat_period.date_to)
        )
        bands_by_period[2000 + i] = [
            RateBand(
                id=band.source.precedence[0],
                period_id=2000 + i,
                min_party=band.min_party,
                max_party=band.max_party,
            )
            for band in flat_period.bands
        ]
    return periods, bands_by_period


class TestPointwiseEquivalence:
    @pytest.mark.parametrize("name", sorted(GRIDS))
    def test_flat_grid_prices_every_point_like_the_lazy_picker(self, name: str) -> None:
        sources = GRIDS[name]
        raw_periods, raw_bands = _raw_context(sources)
        flat_periods, flat_bands = _flat_context(sources)

        lo = min(s.date_from for s in sources) - timedelta(days=1)
        hi = max(s.date_to for s in sources) + timedelta(days=1)
        night = lo
        while night <= hi:
            for party in range(0, 13):
                raw = pick_band_for_night(raw_periods, raw_bands, night, party)
                flat = pick_band_for_night(flat_periods, flat_bands, night, party)
                point = f"{name} night={night} party={party}"
                assert type(raw) is type(flat), point
                if isinstance(raw, Picked):
                    assert isinstance(flat, Picked)
                    assert flat.rule.pk == raw.rule.pk, point
            night += timedelta(days=1)

    @pytest.mark.parametrize("name", sorted(GRIDS))
    def test_flat_grid_is_disjoint(self, name: str) -> None:
        """No (night, party) point is covered by two flat bands — the invariant
        the DB EXCLUDEs enforce for persisted rows."""
        result = flatten_rate_grid(GRIDS[name])
        for a_idx, pa in enumerate(result.periods):
            for pb in result.periods[a_idx + 1 :]:
                assert pa.date_to < pb.date_from or pb.date_to < pa.date_from
            cells = [(b.min_party, b.max_party) for b in pa.bands]
            for i, (alo, ahi) in enumerate(cells):
                assert alo <= ahi
                for blo, bhi in cells[i + 1 :]:
                    assert ahi < blo or bhi < alo
