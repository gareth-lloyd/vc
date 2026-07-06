"""GAP-065 — the `rooms` stage gives a knob-fraction of seeded rooms a
building/floor so the grouped rooms list shows real structure in dev.

Location assignment draws from its **own** `random.Random` (never `ctx.rng`)
so it can't shift the shared stream other stages pin (seed-44 determinism).
"""

from __future__ import annotations

import random
from typing import cast

import pytest

from properties.enums import RoomFloor, RoomPlacement
from properties.factories import PropertyFactory
from properties.models import Property, Room
from seeding.context import _PROFILES, Profile, SeedContext
from seeding.stages.rooms import _run

pytestmark = pytest.mark.django_db


def _ctx(properties: list[Property], profile: Profile = Profile.MIXED) -> SeedContext:
    ctx = SeedContext(
        rng=random.Random(0),
        knobs=_PROFILES[profile],
        n_properties=len(properties),
        n_bookings=0,
        n_users=0,
    )
    ctx.properties.extend(properties)
    return ctx


def _rooms(prop: Property) -> list[Room]:
    return list(Room.objects.filter(property=prop))


def test_knob_fraction_of_rooms_get_location() -> None:
    prop = cast(Property, PropertyFactory())
    _run(_ctx([prop]))

    rooms = _rooms(prop)
    located = [r for r in rooms if r.placement or r.floor]
    assert located, "mixed profile must produce some located rooms"
    valid_placements = set(RoomPlacement.values) | {""}
    valid_floors = set(RoomFloor.values) | {""}
    for room in rooms:
        assert room.placement in valid_placements
        assert room.floor in valid_floors
        assert room.placement_note == ""  # seeding never fakes legacy notes


def test_zero_knob_leaves_location_blank() -> None:
    # (HAPPY itself seeds zero rooms, so the knob-off path is pinned with
    # rooms present; the profile defaults are pinned separately below.)
    prop = cast(Property, PropertyFactory())
    ctx = _ctx([prop], profile=Profile.MIXED)
    ctx.knobs = _PROFILES[Profile.MIXED].__class__(
        name="test", rooms_per_property=(4, 8), rooms_with_location=0.0
    )
    _run(ctx)

    assert all(r.placement == "" and r.floor == "" for r in _rooms(prop))


def test_happy_knob_default_is_off() -> None:
    assert _PROFILES[Profile.HAPPY].rooms_with_location == 0.0
    assert _PROFILES[Profile.MIXED].rooms_with_location > 0.0
    assert _PROFILES[Profile.CHAOS].rooms_with_location > 0.0


def test_location_draws_do_not_perturb_the_shared_ctx_rng() -> None:
    # Same ctx.rng seed, location knob on vs off → identical shared-stream
    # state afterwards (location must use its own Random).
    prop_on = cast(Property, PropertyFactory())
    ctx_on = _ctx([prop_on])
    _run(ctx_on)

    prop_off = cast(Property, PropertyFactory())
    ctx_off = _ctx([prop_off])
    ctx_off.knobs = _PROFILES[Profile.MIXED].__class__(
        name="test",
        rooms_per_property=_PROFILES[Profile.MIXED].rooms_per_property,
        rooms_with_location=0.0,
    )
    _run(ctx_off)

    assert ctx_on.rng.getstate() == ctx_off.rng.getstate()
