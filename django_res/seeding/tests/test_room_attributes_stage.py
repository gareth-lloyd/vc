"""The `room_attributes` stage assigns amenity tags + facet values to seeded
rooms so list views and the room dialog show variety.

See ``seeding/stages/room_attributes.py``.
"""

from __future__ import annotations

import random
from typing import cast

import pytest

from properties.factories import (
    FeatureFactory,
    PropertyFactory,
    RoomAttributeFactory,
    RoomFactory,
)
from properties.models import (
    Feature,
    Property,
    PropertyFeature,
    Room,
    RoomAttribute,
    RoomAttributeAssignment,
)
from seeding.context import _PROFILES, Profile, SeedContext
from seeding.stages.room_attributes import _run

pytestmark = pytest.mark.django_db


def _ctx(properties: list[Property]) -> SeedContext:
    ctx = SeedContext(
        rng=random.Random(0),
        knobs=_PROFILES[Profile.MIXED],
        n_properties=len(properties),
        n_bookings=0,
        n_users=0,
    )
    ctx.properties.extend(properties)
    return ctx


def _seed_rooms(n_rooms: int = 6) -> tuple[Property, list[Room]]:
    prop = cast(Property, PropertyFactory())
    rooms = [
        cast(Room, RoomFactory(property=prop, is_ensuite=(i % 2 == 0))) for i in range(n_rooms)
    ]
    return prop, rooms


def test_assigns_attributes_to_rooms() -> None:
    prop, rooms = _seed_rooms()
    made = _run(_ctx([prop]))
    assert made > 0
    assert RoomAttributeAssignment.objects.filter(room__in=rooms).exists()
    # Per-room cap: at most 4 amenity tags.
    for room in rooms:
        assert room.attribute_links.count() <= 4


def test_derives_property_features_from_implying_attributes() -> None:
    """GAP-067 — after assigning attributes, the stage recomputes each seeded
    property's derived features so seeded data matches API-created properties."""
    # Retire the ambient catalog so our implying attribute is the only pick.
    RoomAttribute.objects.update(is_active=False)
    feature = cast(Feature, FeatureFactory())
    RoomAttributeFactory(implies_property_feature=feature, is_active=True)
    prop, _rooms = _seed_rooms(3)
    ctx = _ctx([prop])
    ctx.knobs = _PROFILES[Profile.MIXED].__class__(name="test", attributes_per_room=(1, 1))

    _run(ctx)

    assert PropertyFeature.objects.filter(property=prop, feature=feature, is_derived=True).exists()


def test_facets_respect_the_ensuite_coherence_constraint() -> None:
    prop, _rooms = _seed_rooms(10)
    _run(_ctx([prop]))
    for room in Room.objects.filter(property=prop):
        if room.ensuite_type:
            assert room.is_ensuite is True


def test_rerun_does_not_duplicate_assignments() -> None:
    prop, rooms = _seed_rooms()
    _run(_ctx([prop]))
    first = RoomAttributeAssignment.objects.filter(room__in=rooms).count()
    _run(_ctx([prop]))
    assert RoomAttributeAssignment.objects.filter(room__in=rooms).count() == first


def test_no_properties_is_a_noop() -> None:
    assert _run(_ctx([])) == 0


def test_zero_knob_disables_the_stage() -> None:
    prop, rooms = _seed_rooms()
    ctx = _ctx([prop])
    ctx.knobs = _PROFILES[Profile.MIXED].__class__(name="test", attributes_per_room=(0, 0))

    assert _run(ctx) == 0
    assert not RoomAttributeAssignment.objects.filter(room__in=rooms).exists()
    # Facet columns stay untouched when the stage is disabled.
    assert all(r.ensuite_type == "" and r.access == "" for r in rooms)


def test_does_not_perturb_the_shared_ctx_rng() -> None:
    # The stage must draw from its own RNG so it never shifts ctx.rng for any
    # stage the runner sequences after it (determinism guard).
    prop, _rooms = _seed_rooms()
    ctx = _ctx([prop])
    before = ctx.rng.getstate()

    _run(ctx)

    assert ctx.rng.getstate() == before
