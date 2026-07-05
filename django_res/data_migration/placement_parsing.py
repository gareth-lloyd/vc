"""GAP-065 — split the legacy free-text `VillaRoomsPlacement.Name` into the
two room-location axes: (building `RoomPlacement`, `RoomFloor` rung).

The legacy field overloaded both axes (plus stray amenity facts and typos)
into one string. Parsing is deliberately conservative: keyword/word matching
only, and anything ambiguous ("Upper level", "Mezzanine") parses to "" — the
caller preserves the raw string in `Room.placement_note`, so an imperfect
parse never loses information.
"""

from __future__ import annotations

import re

from properties.enums import RoomFloor, RoomPlacement

# Word-boundary matching keys on distinctive words joined by `[\s-]` (so
# hyphenated/joined spellings like "Lower-ground" or "Guesthouse" don't fall
# through to a wrong coarser match), and the ordinal floors require a
# floor-context word (`fl?oor` covers the production typo "First foor") so a
# crammed "Second bedroom" never parses as a floor. Order matters only for
# the floor ladder: "lower ground" must be tested before the bare "ground".
_FLOOR_WORD = r"(?:fl?oor|level)"
_FLOOR_PATTERNS: list[tuple[str, str]] = [
    (r"\blower[\s-]+ground\b", RoomFloor.LOWER_GROUND),
    (r"\bground\b", RoomFloor.GROUND),
    (rf"\bfirst[\s-]+{_FLOOR_WORD}", RoomFloor.FIRST),
    (rf"\bsecond[\s-]+{_FLOOR_WORD}", RoomFloor.SECOND),
    (rf"\b(?:third|fourth|fifth)[\s-]+{_FLOOR_WORD}", RoomFloor.THIRD_PLUS),
    # "upper floor/level", "lower level", "mezzanine", "basement" are
    # deliberately absent: ambiguous rungs stay "" (owner steer A2 pending).
]

_BUILDING_PATTERNS: list[tuple[str, str]] = [
    (r"\bmain[\s-]*house\b", RoomPlacement.MAIN_HOUSE),
    (r"\bguest[\s-]*house\b", RoomPlacement.GUEST_HOUSE),
    (r"\bpool[\s-]*house\b", RoomPlacement.POOL_HOUSE),
    (r"\bannexe?\b", RoomPlacement.ANNEX),
    (r"\bcottage\b", RoomPlacement.COTTAGE),
    (r"\bbungalow\b", RoomPlacement.BUNGALOW),
    (r"\bstudio\b", RoomPlacement.STUDIO),
    # One-offs that don't earn an enum member (ticket: don't over-fit) —
    # the raw note keeps the specific word.
    (r"\bloft\b|\bwing\b|\broof[\s-]+terrace\b", RoomPlacement.OTHER),
]


def parse_placement(raw: str | None) -> tuple[str, str]:
    """Return (placement, floor) values parsed from a legacy placement string.

    Either side is "" when not confidently recognised. The building is the
    EARLIEST match in the text (not pattern-list order, so "Guest house
    opposite main house" is the guest house). A bare floor with no building
    word implies the main house (a lone "First floor" always meant the main
    building in the legacy data); nothing recognised → ("", "").
    """
    text = (raw or "").strip().lower()
    if not text:
        return "", ""

    floor = next(
        (value for pattern, value in _FLOOR_PATTERNS if re.search(pattern, text)),
        "",
    )
    building_matches = [
        (match.start(), value)
        for pattern, value in _BUILDING_PATTERNS
        if (match := re.search(pattern, text))
    ]
    placement = min(building_matches)[1] if building_matches else ""
    if not placement and floor:
        placement = RoomPlacement.MAIN_HOUSE
    return placement, floor
