"""Room amenity assignments + facet values for seeded rooms.

Knob: `attributes_per_room` (inclusive range). (0, 0) disables — facet
columns are then left untouched too. Assigns random active `RoomAttribute`
tags to each seeded room and fills the GAP-064 facet columns
(`ensuite_type` only on rooms the `rooms` stage flagged ensuite — the DB
CheckConstraint requires it; `access` anywhere).

This stage draws from its **own** `random.Random`, never `ctx.rng`, so it can
be sequenced anywhere without shifting the shared RNG stream that other
stages depend on for reproducibility.
"""

from __future__ import annotations

import random

from properties.enums import EnsuiteType, RoomAccess
from properties.models import Room, RoomAttribute, RoomAttributeAssignment
from seeding.context import SeedContext
from seeding.registry import Stage, register

# Stable, private seed: reproducible per room list, decoupled from ctx.rng.
_ATTR_SEED = 0x600D2007


def _run(ctx: SeedContext) -> int:
    low, high = ctx.knobs.attributes_per_room
    if high <= 0:
        return 0
    if not ctx.properties:
        return 0
    catalogue = list(RoomAttribute.objects.filter(is_active=True).order_by("pk"))
    rooms = list(Room.objects.filter(property__in=ctx.properties).order_by("pk"))
    if not catalogue or not rooms:
        return 0
    rng = random.Random(_ATTR_SEED)
    made = 0
    for room in rooms:
        n = rng.randint(low, min(high, len(catalogue)))
        # Top up to the target, so a re-run against a grown catalog can never
        # push a room past the per-room cap.
        budget = max(0, n - room.attribute_links.count())
        for attr in rng.sample(catalogue, k=n)[:budget]:
            _, created = RoomAttributeAssignment.objects.get_or_create(room=room, attribute=attr)
            if created:
                made += 1
        # Facets: a typed ensuite requires is_ensuite (DB constraint), so only
        # rooms the `rooms` stage flagged ensuite draw a type.
        ensuite_type = rng.choice([*EnsuiteType.values, ""]) if room.is_ensuite else ""
        access = rng.choice([*RoomAccess.values, ""])
        if (room.ensuite_type, room.access) != (ensuite_type, access):
            room.ensuite_type = ensuite_type
            room.access = access
            room.save(update_fields=["ensuite_type", "access"])
    return made


register(Stage(name="room_attributes", run=_run, depends_on=("rooms",)))
