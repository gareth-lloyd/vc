"""Bedrooms + bed configurations per property.

Knobs: `rooms_per_property` (inclusive range; (0, 0) disables — the legacy
`happy` profile leaves rooms unseeded) and `rooms_with_location` (fraction of
rooms given a building/floor, GAP-065, so the grouped rooms list shows real
structure; location draws use their **own** `random.Random`, never `ctx.rng`,
so the shared stream other stages pin stays untouched).
"""

from __future__ import annotations

import random
from typing import Any, cast

from properties.enums import RoomFloor, RoomPlacement
from properties.factories import RoomFactory
from properties.models import Room
from seeding.context import SeedContext
from seeding.registry import Stage, register

# Stable, private seed for location draws: reproducible, decoupled from ctx.rng.
_LOCATION_SEED = 0x600D0065

# Weighted toward the common legacy shapes (main house, ground/first) with a
# minority of other buildings/rungs so grouping shows real variety. A small
# blank share on each axis keeps partially-known rooms in the mix.
_PLACEMENTS: list[str] = [
    RoomPlacement.MAIN_HOUSE,
    RoomPlacement.GUEST_HOUSE,
    RoomPlacement.COTTAGE,
    RoomPlacement.ANNEX,
    RoomPlacement.POOL_HOUSE,
    RoomPlacement.BUNGALOW,
    RoomPlacement.STUDIO,
    RoomPlacement.OTHER,
    "",
]
_PLACEMENT_WEIGHTS = [50, 14, 8, 7, 4, 3, 3, 3, 8]
_FLOORS: list[str] = [
    RoomFloor.GROUND,
    RoomFloor.FIRST,
    RoomFloor.SECOND,
    RoomFloor.LOWER_GROUND,
    RoomFloor.THIRD_PLUS,
    "",
]
_FLOOR_WEIGHTS = [38, 34, 10, 5, 2, 11]


def _assign_locations(ctx: SeedContext) -> None:
    share = ctx.knobs.rooms_with_location
    if share <= 0:
        return
    rng = random.Random(_LOCATION_SEED)
    rooms = Room.objects.filter(property__in=ctx.properties).order_by("pk")
    for room in rooms:
        if rng.random() >= share:
            continue
        placement = rng.choices(_PLACEMENTS, weights=_PLACEMENT_WEIGHTS)[0]
        floor = rng.choices(_FLOORS, weights=_FLOOR_WEIGHTS)[0]
        if (room.placement, room.floor) != (placement, floor):
            room.placement = placement
            room.floor = floor
            room.save(update_fields=["placement", "floor"])


def _run(ctx: SeedContext) -> int:
    low, high = ctx.knobs.rooms_per_property
    if high <= 0:
        return 0
    if not ctx.properties:
        return 0
    made = 0
    for prop in ctx.properties:
        n_rooms = ctx.rng.randint(low, high)
        for i in range(n_rooms):
            # Mix ensuites and bed configurations so list views show variety.
            is_ensuite = ctx.rng.random() < 0.5
            # factory-boy is untyped; cast the built row to its model for mypy.
            room = cast(Any, RoomFactory(property=prop, is_ensuite=is_ensuite))
            # RoomFactory already creates a `RoomBeds(double=1)` row; vary it.
            beds = room.beds
            choice = ctx.rng.choice(("double", "twin", "bunk", "single"))
            beds.double = 1 if choice == "double" else 0
            beds.twin = 2 if choice == "twin" else 0
            beds.bunk = 1 if choice == "bunk" else 0
            beds.single = 1 if choice == "single" else 0
            beds.save(update_fields=["double", "twin", "bunk", "single"])
            # Keep room ordering predictable.
            if room.sort_order != i:
                room.sort_order = i
                room.save(update_fields=["sort_order"])
            made += 1
    _assign_locations(ctx)
    return made


register(Stage(name="rooms", run=_run, depends_on=("properties",)))
