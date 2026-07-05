"""Pure tests for `resolve_rate_band_overlaps` — dict fixtures, no DB.

Since BUG-016 the resolver is pre-normalisation only: the junk pre-filter,
the checkout-convention boundary trim, and a same-discriminator dedupe that
keeps dirty input clear of the flattener's duplicate-precedence ValueError.
Conflict resolution (approved-first / lowest-ID, split not clip) lives in the
shared `pricing.services.flattening` flattener — see
`pricing/tests/test_flattening.py` and the loader-seam tests in
`test_rate_band_loader.py`.
"""

from __future__ import annotations

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


def test_identical_rows_drop_duplicate() -> None:
    """Two rows sharing the same discriminator (same ID, no `_legacy_id`) —
    unreachable off real SQL PKs, but dirty input must not reach the
    flattener's duplicate-precedence ValueError. Keep the first."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 10), PartySize=4),
            _row(1, date(2025, 6, 1), date(2025, 6, 10), PartySize=4),
        ]
    )
    assert _spans(res.rows) == [(1, date(2025, 6, 1), date(2025, 6, 10))]
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


def test_seasons_trim_independently() -> None:
    """The boundary trim is scoped per season: a contiguous boundary against a
    row in a *different* season never trims."""
    res = resolve_rate_band_overlaps(
        [
            _row(1, date(2025, 6, 1), date(2025, 6, 8), SeasonId=42),
            _row(2, date(2025, 6, 8), date(2025, 6, 15), SeasonId=43),
        ]
    )
    assert _spans(res.rows) == [
        (1, date(2025, 6, 1), date(2025, 6, 8)),
        (2, date(2025, 6, 8), date(2025, 6, 15)),
    ]
    assert res.trimmed == 0


def test_occupancy_bands_disjoint_both_survive() -> None:
    """Sibling occupancy bands pass through pre-normalisation untouched —
    identical spans can never boundary-trim (the trim gate needs one row to
    START on the other's end), and conflict resolution now happens later, in
    the flattener."""
    res = resolve_rate_band_overlaps(
        [
            _row(101, date(2025, 6, 1), date(2025, 6, 10), _occ_band=(2, 4)),
            _row(102, date(2025, 6, 1), date(2025, 6, 10), _occ_band=(5, 6)),
        ]
    )
    assert [r["ID"] for r in res.rows] == [101, 102]
    assert (res.trimmed, res.dropped) == (0, 0)
    # The explicit band range is carried through to `_row_to_band`.
    assert res.rows[0]["_occ_band"] == (2, 4)
    assert res.rows[1]["_occ_band"] == (5, 6)
