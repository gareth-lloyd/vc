"""Unit tests for `_prepare_occupancy_rows` — the pure expansion of a
VillaSeasonRate x VillaOccupencyPrice LEFT JOIN into the flat row set the
overlap resolver + `transform` consume (BUG-013).

DB-free: hand-rolled dict fixtures mirror the loader's `legacy_query` output.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from data_migration.loaders.pricing import _prepare_occupancy_rows


def _join_row(**overrides: Any) -> dict[str, Any]:
    """One LEFT JOIN row: parent VillaSeasonRate columns + optional child
    VillaOccupencyPrice columns (`OccId`/`OccupencyFrom`/`OccupencyTo`/
    `OccupencyPrice`, all None for a parent with no matching child)."""
    base: dict[str, Any] = {
        "ID": 10,
        "SeasonId": 42,
        "FromDate": date(2025, 6, 1),
        "ToDate": date(2025, 6, 14),
        "PartySize": None,
        "IsPOA": False,
        "WeeklyPrice": Decimal("1000"),
        "NightlyPrice": None,
        "Price": None,
        "IsApprove": True,
        "IsOccupationPrice": True,
        "Description": "Peak",
        "OccId": None,
        "OccupencyFrom": None,
        "OccupencyTo": None,
        "OccupencyPrice": None,
    }
    base.update(overrides)
    return base


def _by_legacy_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r["_legacy_id"]): r for r in rows if "_legacy_id" in r}


def test_banded_parent_emits_band_rows_plus_gap_fallbacks() -> None:
    rows = [
        _join_row(OccId=101, OccupencyFrom=2, OccupencyTo=4, OccupencyPrice=Decimal("500")),
        _join_row(OccId=102, OccupencyFrom=5, OccupencyTo=6, OccupencyPrice=Decimal("700")),
    ]

    out = _prepare_occupancy_rows(rows)

    by_id = _by_legacy_id(out)
    # Two band rows carrying their own party range + weekly price.
    band1 = by_id["occ-101"]
    assert band1["ID"] == 101
    assert band1["_occ_band"] == (2, 4)
    assert band1["WeeklyPrice"] == Decimal("500")
    # Nightly is left unset — the engine derives it from weekly identically.
    assert band1["NightlyPrice"] is None
    assert band1["Price"] is None
    assert band1["IsPOA"] is False
    band2 = by_id["occ-102"]
    assert band2["_occ_band"] == (5, 6)
    assert band2["WeeklyPrice"] == Decimal("700")
    assert band2["NightlyPrice"] is None

    # Two gap fallbacks (below the first band, above the last) carrying the
    # parent's base weekly price. The upper gap is open-topped (capacity clamp
    # happens later, in transform).
    fb0 = by_id["occ-fb-10-0"]
    assert fb0["ID"] == 10
    assert fb0["_occ_band"] == (1, 1)
    assert fb0["WeeklyPrice"] == Decimal("1000")
    fb1 = by_id["occ-fb-10-1"]
    assert fb1["_occ_band"] == (7, None)
    assert fb1["WeeklyPrice"] == Decimal("1000")

    assert len(out) == 4


def test_invalid_child_is_dropped_and_covered_by_fallback() -> None:
    """A null/≤0-bound child (OccupencyFrom/To DB-default to 0) is dropped, not
    coerced — its party range is instead covered by the base-weekly fallback."""
    rows = [
        _join_row(OccId=101, OccupencyFrom=2, OccupencyTo=4, OccupencyPrice=Decimal("500")),
        _join_row(OccId=102, OccupencyFrom=0, OccupencyTo=0, OccupencyPrice=Decimal("700")),
        _join_row(OccId=103, OccupencyFrom=None, OccupencyTo=6, OccupencyPrice=Decimal("700")),
        _join_row(OccId=104, OccupencyFrom=6, OccupencyTo=3, OccupencyPrice=Decimal("700")),
    ]

    out = _prepare_occupancy_rows(rows)

    by_id = _by_legacy_id(out)
    assert set(by_id) == {"occ-101", "occ-fb-10-0", "occ-fb-10-1"}
    # Only band (2,4) survives → gaps (1,1) and (5,None) fall to the fallback.
    assert by_id["occ-fb-10-0"]["_occ_band"] == (1, 1)
    assert by_id["occ-fb-10-1"]["_occ_band"] == (5, None)


def test_simple_row_passes_through_unchanged() -> None:
    simple = _join_row(ID=7, PartySize=4, IsOccupationPrice=False, OccId=None)
    out = _prepare_occupancy_rows([simple])
    assert out == [simple]
    assert "_occ_band" not in out[0]
    assert "_legacy_id" not in out[0]


def test_non_occupancy_parent_ignores_orphan_children() -> None:
    """A rate not flagged `IsOccupationPrice` keeps its flat base price even if
    stray VillaOccupencyPrice rows exist — legacy never reads them, and the
    LEFT JOIN must collapse the duplicated rows back to one base row."""
    rows = [
        _join_row(
            IsOccupationPrice=False,
            OccId=101,
            OccupencyFrom=2,
            OccupencyTo=4,
            OccupencyPrice=Decimal("300"),
        ),
        _join_row(
            IsOccupationPrice=False,
            OccId=102,
            OccupencyFrom=5,
            OccupencyTo=6,
            OccupencyPrice=Decimal("400"),
        ),
    ]
    out = _prepare_occupancy_rows(rows)
    assert len(out) == 1
    assert out[0]["WeeklyPrice"] == Decimal("1000")
    assert "_occ_band" not in out[0]


def test_zero_price_band_dropped_and_covered_by_fallback() -> None:
    """A valid-bounds band with a null/0 price prices nobody in legacy; it is
    dropped so the base-weekly fallback covers its party range (no hole)."""
    rows = [
        _join_row(OccId=101, OccupencyFrom=2, OccupencyTo=4, OccupencyPrice=Decimal("500")),
        _join_row(OccId=102, OccupencyFrom=5, OccupencyTo=6, OccupencyPrice=Decimal("0")),
        _join_row(OccId=103, OccupencyFrom=7, OccupencyTo=8, OccupencyPrice=None),
    ]
    out = _prepare_occupancy_rows(rows)
    by_id = _by_legacy_id(out)
    assert set(by_id) == {"occ-101", "occ-fb-10-0", "occ-fb-10-1"}
    # Only band (2,4) survives → the (5,6)/(7,8) ranges fall to the fallback,
    # whose gaps are (1,1) and (5,None).
    assert by_id["occ-fb-10-0"]["_occ_band"] == (1, 1)
    assert by_id["occ-fb-10-1"]["_occ_band"] == (5, None)


def test_childless_banded_parent_passes_through_as_base_weekly() -> None:
    """A parent flagged occupancy but with no VillaOccupencyPrice children
    joins to a single OccId-null row — the plain base-weekly path."""
    parent = _join_row(ID=9, OccId=None)
    out = _prepare_occupancy_rows([parent])
    assert out == [parent]


def test_band_covering_from_one_has_no_below_gap() -> None:
    rows = [_join_row(OccId=201, OccupencyFrom=1, OccupencyTo=4, OccupencyPrice=Decimal("500"))]
    out = _prepare_occupancy_rows(rows)
    by_id = _by_legacy_id(out)
    assert by_id["occ-201"]["_occ_band"] == (1, 4)
    # Only the above-band gap remains.
    fallbacks = [r for k, r in by_id.items() if k.startswith("occ-fb")]
    assert len(fallbacks) == 1
    assert fallbacks[0]["_occ_band"] == (5, None)


def test_overlapping_bands_gap_is_complement_of_union() -> None:
    rows = [
        _join_row(OccId=301, OccupencyFrom=2, OccupencyTo=4, OccupencyPrice=Decimal("500")),
        _join_row(OccId=302, OccupencyFrom=3, OccupencyTo=6, OccupencyPrice=Decimal("600")),
    ]
    out = _prepare_occupancy_rows(rows)
    gaps = sorted(r["_occ_band"] for k, r in _by_legacy_id(out).items() if k.startswith("occ-fb"))
    # Union of (2,4)+(3,6) = (2,6): gaps are (1,1) below and (7,None) above.
    assert gaps == [(1, 1), (7, None)]


def test_multiple_parents_grouped_independently_order_preserved() -> None:
    rows = [
        _join_row(ID=10, OccId=101, OccupencyFrom=2, OccupencyTo=4, OccupencyPrice=Decimal("500")),
        _join_row(ID=20, PartySize=2, OccId=None),
    ]
    out = _prepare_occupancy_rows(rows)
    # Parent 10 expands (bands + fallbacks) before the untouched simple parent 20.
    assert out[-1]["ID"] == 20 and "_occ_band" not in out[-1]
    by_id = _by_legacy_id(out)
    assert "occ-101" in by_id
