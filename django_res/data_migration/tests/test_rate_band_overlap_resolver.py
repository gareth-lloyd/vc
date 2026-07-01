"""Pure tests for `resolve_rate_band_overlaps` — dict fixtures, no DB.

Legacy had no precedence concept (unordered TOP 1), so the resolver turns
overlapping VillaSeasonRate rows into a disjoint set at load time:
boundary trim for checkout-style contiguous bands, then approved-first /
earliest-ID clip-only conflict resolution.
"""

from __future__ import annotations

import random
from datetime import date
from decimal import Decimal
from typing import Any

from data_migration.loaders.pricing import resolve_rate_band_overlaps


def _row(id: int, frm: date | None, to: date | None, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "ID": id,
        "VillaId": 7,
        "SeasonId": 42,
        "CurrencyId": 2,
        "FromDate": frm,
        "ToDate": to,
        "PartySize": None,
        "IsPOA": False,
        "WeeklyPrice": Decimal("1000"),
        "NightlyPrice": None,
        "Price": None,
        "PriceType": 1,
        "IsExTra": False,
        "IsApprove": True,
        "IsAvailable": True,
        "Description": "",
    }
    base.update(overrides)
    return base


def _spans(rows: list[dict[str, Any]]) -> list[tuple[int, date, date]]:
    return [(r["ID"], r["FromDate"], r["ToDate"]) for r in rows]


def test_boundary_trim_checkout_convention() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 8)),
            _row(2, date(2025, 6, 8), date(2025, 6, 15)),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 1), date(2025, 6, 7)),
        (2, date(2025, 6, 8), date(2025, 6, 15)),
    ]
    assert res.trimmed == 1
    assert res.dropped == 0


def test_touching_disjoint_party_brackets_not_trimmed() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 8), PartySize=2),
            _row(2, date(2025, 6, 8), date(2025, 6, 15), PartySize=4),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 1), date(2025, 6, 8)),
        (2, date(2025, 6, 8), date(2025, 6, 15)),
    ]
    assert res.trimmed == 0


def test_boundary_trim_chain() -> None:
    """A→B→C contiguous chain: A and B trim, C keeps its end."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 8)),
            _row(2, date(2025, 6, 8), date(2025, 6, 15)),
            _row(3, date(2025, 6, 15), date(2025, 6, 22)),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 1), date(2025, 6, 7)),
        (2, date(2025, 6, 8), date(2025, 6, 14)),
        (3, date(2025, 6, 15), date(2025, 6, 22)),
    ]
    assert res.trimmed == 2


def test_boundary_trim_to_empty_drops_row() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 2)),
            _row(2, date(2025, 6, 2), date(2025, 6, 9)),
        ]
    )
    assert _spans(res.rows) == [(2, date(2025, 6, 2), date(2025, 6, 9))]
    assert res.dropped == 1


def test_fully_covered_row_dropped() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 30)),
            _row(2, date(2025, 6, 10), date(2025, 6, 20)),
        ]
    )
    assert _spans(res.rows) == [(1, date(2025, 6, 1), date(2025, 6, 30))]
    assert res.dropped == 1


def test_partial_overlap_clips_later_id() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10)),
            _row(2, date(2025, 6, 5), date(2025, 6, 20)),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 1), date(2025, 6, 10)),
        (2, date(2025, 6, 11), date(2025, 6, 20)),
    ]
    assert res.trimmed == 1
    assert res.dropped == 0


def test_mid_punch_keeps_larger_side() -> None:
    """A winner strictly inside a loser: clip-only keeps the loser's larger side."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 10), date(2025, 6, 12)),
            _row(2, date(2025, 6, 1), date(2025, 6, 30)),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 10), date(2025, 6, 12)),
        (2, date(2025, 6, 13), date(2025, 6, 30)),
    ]
    assert res.trimmed == 1


def test_approved_later_row_beats_unapproved_earlier_row() -> None:
    """Approved rows claim space first even against a lower legacy ID."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), IsApprove=False),
            _row(2, date(2025, 6, 5), date(2025, 6, 20), IsApprove=True),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 1), date(2025, 6, 4)),
        (2, date(2025, 6, 5), date(2025, 6, 20)),
    ]


def test_unapproved_rows_resolve_earliest_id_wins() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), IsApprove=False),
            _row(2, date(2025, 6, 5), date(2025, 6, 20), IsApprove=False),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 1), date(2025, 6, 10)),
        (2, date(2025, 6, 11), date(2025, 6, 20)),
    ]


def test_nested_party_null_winner_drops_specific_loser() -> None:
    """A NULL-party winner ([1, capacity]) fully covers a specific bracket."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), PartySize=None),
            _row(2, date(2025, 6, 1), date(2025, 6, 10), PartySize=4),
        ]
    )
    assert [r["ID"] for r in res.rows] == [1]
    assert res.dropped == 1


def test_nested_party_specific_winner_clips_null_loser() -> None:
    """A [q..q] winner punches the NULL row: upper interval first, lower as fallback."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), PartySize=4),
            _row(2, date(2025, 6, 1), date(2025, 6, 10), PartySize=None),
        ]
    )
    assert [r["ID"] for r in res.rows] == [1, 2]
    assert res.rows[1]["_party_intervals"] == [(5, None), (1, 3)]
    assert res.party_clipped == 1


def test_second_party_clip_preserves_uncovered_brackets() -> None:
    """Successive party clips subtract from the full remaining interval set —
    a bracket no winner covers must survive, not vanish on the second clip."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), PartySize=2),
            _row(2, date(2025, 6, 1), date(2025, 6, 10), PartySize=5),
            _row(3, date(2025, 6, 1), date(2025, 6, 10), PartySize=None),
        ]
    )
    assert [r["ID"] for r in res.rows] == [1, 2, 3]
    assert res.rows[2]["_party_intervals"] == [(6, None), (3, 4), (1, 1)]
    assert res.party_clipped == 2


def test_party_clip_remainders_conflict_checked_on_identical_dates() -> None:
    """A clipped row's *whole* interval set claims space: a later row landing
    inside any remainder interval is resolved, so no interval `transform` can
    pick ever overlaps another loaded rule."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), PartySize=5),
            _row(2, date(2025, 6, 1), date(2025, 6, 10), PartySize=None),
            _row(3, date(2025, 6, 1), date(2025, 6, 10), PartySize=3),
        ]
    )
    # Row 2's remainders [(6, None), (1, 4)] cover row 3's (3, 3) → dropped.
    assert [r["ID"] for r in res.rows] == [1, 2]
    assert res.rows[1]["_party_intervals"] == [(6, None), (1, 4)]
    assert res.dropped == 1


def test_party_clip_remainders_conflict_checked_on_date_overlap() -> None:
    """Date conflicts also test against every remainder interval, not just the
    preferred one — row 3's (2, 2) sits inside row 2's fallback (1, 4)."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), PartySize=5),
            _row(2, date(2025, 6, 1), date(2025, 6, 10), PartySize=None),
            _row(3, date(2025, 6, 5), date(2025, 6, 20), PartySize=2),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 1), date(2025, 6, 10)),
        (2, date(2025, 6, 1), date(2025, 6, 10)),
        (3, date(2025, 6, 11), date(2025, 6, 20)),
    ]


def test_identical_rows_drop_duplicate() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), PartySize=4),
            _row(2, date(2025, 6, 1), date(2025, 6, 10), PartySize=4),
        ]
    )
    assert [r["ID"] for r in res.rows] == [1]
    assert res.dropped == 1


def test_priceless_row_excluded_and_cannot_trim() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 8)),
            _row(
                2,
                date(2025, 6, 8),
                date(2025, 6, 15),
                WeeklyPrice=None,
                NightlyPrice=None,
                Price=None,
                IsPOA=False,
            ),
        ]
    )
    assert _spans(res.rows) == [(1, date(2025, 6, 1), date(2025, 6, 8))]
    assert res.trimmed == 0
    assert res.dropped == 0  # pre-filtered junk is not a resolver drop


def test_junk_dates_excluded_without_counting() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 8)),
            _row(2, None, date(2025, 6, 15)),
            _row(3, date(2025, 6, 20), date(2025, 6, 20)),
            _row(4, date(2025, 6, 22), date(2025, 6, 21)),
        ]
    )
    assert [r["ID"] for r in res.rows] == [1]
    assert res.dropped == 0


def test_seasons_resolve_independently() -> None:
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), SeasonId=42),
            _row(2, date(2025, 6, 5), date(2025, 6, 20), SeasonId=43),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 1), date(2025, 6, 10)),
        (2, date(2025, 6, 5), date(2025, 6, 20)),
    ]


def _mixed_fixture() -> list[dict[str, Any]]:
    return [
        _row(1, date(2025, 6, 1), date(2025, 6, 8)),
        _row(2, date(2025, 6, 8), date(2025, 6, 15)),
        _row(3, date(2025, 6, 10), date(2025, 6, 20), IsApprove=False),
        _row(4, date(2025, 7, 1), date(2025, 7, 10), PartySize=4),
        _row(5, date(2025, 7, 1), date(2025, 7, 10), PartySize=None),
        _row(6, date(2025, 8, 1), date(2025, 8, 31), SeasonId=43),
        _row(7, date(2025, 8, 10), date(2025, 8, 12), SeasonId=43, IsApprove=False),
    ]


def test_input_order_does_not_change_output() -> None:
    baseline = resolve_rate_band_overlaps(_mixed_fixture())
    shuffled = _mixed_fixture()
    random.Random(42).shuffle(shuffled)
    assert resolve_rate_band_overlaps(shuffled) == baseline


def test_occupancy_bands_disjoint_both_survive() -> None:
    """Sibling occupancy bands share the parent daterange but are disjoint in
    party (by construction), so neither trims nor clips the other."""
    res = resolve_rate_band_overlaps(
        [
            _row(101, date(2025, 6, 1), date(2025, 6, 10), _occ_band=(2, 4)),
            _row(102, date(2025, 6, 1), date(2025, 6, 10), _occ_band=(5, 6)),
        ]
    )
    assert [r["ID"] for r in res.rows] == [101, 102]
    assert (res.trimmed, res.dropped, res.party_clipped) == (0, 0, 0)
    # The explicit band range is carried through to transform.
    assert res.rows[0]["_occ_band"] == (2, 4)
    assert res.rows[1]["_occ_band"] == (5, 6)


def test_occupancy_band_clipped_by_overlapping_period() -> None:
    """A band still resolves against a date-overlapping rule on the same card:
    the lower-ID simple rule wins, the band keeps the uncovered remainder."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 20), PartySize=None),
            _row(101, date(2025, 6, 10), date(2025, 6, 30), _occ_band=(2, 4)),
        ]
    )
    band = next(r for r in res.rows if r["ID"] == 101)
    assert (band["FromDate"], band["ToDate"]) == (date(2025, 6, 21), date(2025, 6, 30))
    assert (1, date(2025, 6, 1), date(2025, 6, 20)) in _spans(res.rows)


def test_occupancy_id_collision_is_order_independent() -> None:
    """A band's OccId can numerically equal a simple row's ID; the conflict is
    then broken by the unique `_legacy_id` discriminator, not input order."""

    def fixture() -> list[dict[str, Any]]:
        return [
            _row(42, date(2025, 6, 1), date(2025, 6, 10), _occ_band=(3, 5), _legacy_id="occ-42"),
            _row(42, date(2025, 6, 1), date(2025, 6, 10), PartySize=None, _legacy_id="42"),
        ]

    first = resolve_rate_band_overlaps(fixture())
    second = resolve_rate_band_overlaps(list(reversed(fixture())))
    assert first == second


def test_resolved_output_is_a_fixed_point_for_date_overlaps() -> None:
    first = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 8)),
            _row(2, date(2025, 6, 8), date(2025, 6, 15)),
            _row(3, date(2025, 6, 10), date(2025, 6, 20)),
        ]
    )
    second = resolve_rate_band_overlaps(first.rows)
    assert second.rows == first.rows
    assert (second.trimmed, second.dropped, second.party_clipped) == (0, 0, 0)
