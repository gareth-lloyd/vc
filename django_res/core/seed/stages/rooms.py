"""Bedrooms + bed configurations per property.

Knob: `rooms_per_property` (inclusive range). (0, 0) disables — the legacy
`happy` profile leaves rooms unseeded.
"""

from __future__ import annotations

from typing import Any, cast

from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from properties.factories import RoomFactory


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
    return made


register(Stage(name="rooms", run=_run, depends_on=("properties",)))
