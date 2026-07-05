"""GAP-065 — `parse_placement`: split the legacy free-text
`VillaRoomsPlacement.Name` into the (building, floor) axes.

The table below covers every distinct concept in the production-dump evidence
recorded in the GAP-065 ticket, including the crammed-facts strings and the
known typos. Ambiguous floors (upper/lower level, mezzanine, basement) parse
to "" — the raw string survives in `placement_note`, so nothing is lost.
"""

from __future__ import annotations

import pytest

from data_migration.placement_parsing import parse_placement

CASES = [
    # --- floor axis (bare floor → implicitly the main house) ---
    ("Ground floor", ("main_house", "ground")),
    ("Ground level", ("main_house", "ground")),
    ("First floor", ("main_house", "first")),
    ("Second floor", ("main_house", "second")),
    ("Lower ground", ("main_house", "lower_ground")),
    ("Third floor", ("main_house", "third_plus")),
    # typo in the production data — word matching shrugs it off
    ("First foor", ("main_house", "first")),
    # --- ambiguous floors: leave blank, the preserved raw note carries it ---
    ("Upper floor", ("", "")),
    ("Upper level", ("", "")),
    ("Lower level", ("", "")),
    ("Mezzanine", ("", "")),
    ("Basement", ("", "")),
    # --- building axis (no floor) ---
    ("Main house", ("main_house", "")),
    ("Guest house", ("guest_house", "")),
    ("Pool house", ("pool_house", "")),
    ("Annexe", ("annex", "")),
    ("Annex", ("annex", "")),
    ("Cottage", ("cottage", "")),
    ("Bungalow", ("bungalow", "")),
    ("Studio", ("studio", "")),
    # one-offs that don't earn an enum member (ticket: don't over-fit)
    ("Loft", ("other", "")),
    ("Wing", ("other", "")),
    ("Roof terrace", ("other", "")),
    # --- both axes in one string ---
    ("First floor of the guest house", ("guest_house", "first")),
    ("Guest house, ground floor", ("guest_house", "ground")),
    ("Ground floor annexe", ("annex", "ground")),
    # --- crammed facts: location still parses; the rest rides the raw note ---
    ("First floor. Ceiling fan", ("main_house", "first")),
    ("Ground floor. Mini fridge, safe", ("main_house", "ground")),
    ("First floor - King, hairdryer", ("main_house", "first")),
    ("Ground floor. Mosquito nets", ("main_house", "ground")),
    ("First floor. Superking bed.", ("main_house", "first")),
    ("First floor. Wifi", ("main_house", "first")),
    # --- hyphenated / joined spellings must not downgrade to a wrong match ---
    ("Lower-ground floor", ("main_house", "lower_ground")),
    ("Guest-house", ("guest_house", "")),
    ("Guesthouse, first floor", ("guest_house", "first")),
    ("First-floor", ("main_house", "first")),
    # --- bare ordinals without floor context are NOT floors ---
    ("Second bedroom on the left", ("", "")),
    ("First of two twin rooms", ("", "")),
    # --- building picked by text position, not pattern-list order ---
    ("Guest house opposite main house", ("guest_house", "")),
    ("Annexe behind the main house", ("annex", "")),
    # --- nothing recognisable / degenerate input ---
    ("Sea view", ("", "")),
    ("", ("", "")),
    (None, ("", "")),
    # case-insensitive
    ("GROUND FLOOR", ("main_house", "ground")),
    ("guest HOUSE first floor", ("guest_house", "first")),
]


@pytest.mark.parametrize(("raw", "expected"), CASES, ids=lambda v: repr(v))
def test_parse_placement(raw: str | None, expected: tuple[str, str]) -> None:
    assert parse_placement(raw) == expected


def test_lower_ground_is_not_ground() -> None:
    # "lower ground" must win over the bare "ground" keyword.
    assert parse_placement("Lower ground floor") == ("main_house", "lower_ground")
