"""GAP-065 — room location: building (`placement`) + floor axes.

`placement` loses its dishonest `MAIN_HOUSE` default and becomes blank-able
("" = unknown, same posture as `ensuite_type`/`access`); `floor` is a fixed
ladder; `placement_note` preserves the raw legacy placement string.
"""

from __future__ import annotations

from typing import cast

import pytest
from django.core.exceptions import ValidationError

from properties.enums import RoomFloor, RoomPlacement
from properties.factories import PropertyFactory, RoomFactory
from properties.models import Property, Room

pytestmark = pytest.mark.django_db


def _room(**kwargs: object) -> Room:
    return cast(Room, RoomFactory(**kwargs))


class TestEnums:
    def test_placement_gains_building_members(self) -> None:
        assert RoomPlacement.COTTAGE == "cottage"
        assert RoomPlacement.BUNGALOW == "bungalow"
        assert RoomPlacement.STUDIO == "studio"

    def test_annex_relabelled_annexe(self) -> None:
        # Value stays "annex" (no row churn); label follows the legacy data.
        assert RoomPlacement.ANNEX == "annex"
        assert RoomPlacement.ANNEX.label == "Annexe"

    def test_floor_ladder(self) -> None:
        assert [choice[0] for choice in RoomFloor.choices] == [
            "lower_ground",
            "ground",
            "first",
            "second",
            "third_plus",
        ]


class TestRoomLocationFields:
    def test_room_saves_with_all_location_fields_blank(self) -> None:
        prop = cast(Property, PropertyFactory())
        room = Room.objects.create(property=prop, name="Blank room")
        room.full_clean()
        assert room.placement == ""
        assert room.floor == ""
        assert room.placement_note == ""

    def test_placement_and_floor_persist(self) -> None:
        room = _room(
            placement=RoomPlacement.GUEST_HOUSE,
            floor=RoomFloor.FIRST,
            placement_note="First floor of the guest house",
        )
        room.refresh_from_db()
        assert room.placement == RoomPlacement.GUEST_HOUSE
        assert room.floor == RoomFloor.FIRST
        assert room.placement_note == "First floor of the guest house"

    def test_invalid_floor_rejected_by_validation(self) -> None:
        room = _room(floor="mezzanine")
        with pytest.raises(ValidationError):
            room.full_clean()

    def test_factory_default_placement_is_blank(self) -> None:
        assert _room().placement == ""
