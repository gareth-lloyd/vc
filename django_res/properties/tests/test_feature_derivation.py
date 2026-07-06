"""GAP-067 — `recompute_derived_features`: derive property features from the
room attributes assigned across a property's rooms.

The desired derived set = the `implies_property_feature` of every RoomAttribute
assigned to any of the property's rooms (where that FK is non-NULL). The service
manages ONLY `is_derived=True` links: it adds missing ones, deletes ones no
longer implied, and never touches manual (`is_derived=False`) rows.
"""

from __future__ import annotations

from typing import cast

import pytest

from properties.factories import FeatureFactory, PropertyFactory, RoomAttributeFactory, RoomFactory
from properties.models import (
    Feature,
    Property,
    PropertyFeature,
    Room,
    RoomAttribute,
    RoomAttributeAssignment,
)
from properties.services.features import recompute_derived_features

pytestmark = pytest.mark.django_db


def _feature() -> Feature:
    return cast(Feature, FeatureFactory())


def _property() -> Property:
    return cast(Property, PropertyFactory())


def _room(prop: Property) -> Room:
    return cast(Room, RoomFactory(property=prop))


def _assign(room: Room, *, implies: Feature | None) -> RoomAttributeAssignment:
    attr = cast(RoomAttribute, RoomAttributeFactory(implies_property_feature=implies))
    return RoomAttributeAssignment.objects.create(room=room, attribute=attr)


def test_implied_attribute_creates_a_derived_link() -> None:
    prop = _property()
    feature = _feature()
    _assign(_room(prop), implies=feature)

    recompute_derived_features(prop)

    link = PropertyFeature.objects.get(property=prop, feature=feature)
    assert link.is_derived is True


def test_recompute_is_idempotent() -> None:
    prop = _property()
    feature = _feature()
    _assign(_room(prop), implies=feature)

    recompute_derived_features(prop)
    recompute_derived_features(prop)

    assert PropertyFeature.objects.filter(property=prop, feature=feature).count() == 1


def test_attribute_without_implication_creates_nothing() -> None:
    prop = _property()
    _assign(_room(prop), implies=None)

    recompute_derived_features(prop)

    assert not PropertyFeature.objects.filter(property=prop).exists()


def test_removing_the_assignment_drops_the_derived_link() -> None:
    prop = _property()
    feature = _feature()
    assignment = _assign(_room(prop), implies=feature)
    recompute_derived_features(prop)

    assignment.delete()
    recompute_derived_features(prop)

    assert not PropertyFeature.objects.filter(property=prop, feature=feature).exists()


def test_manual_feature_also_implied_stays_manual_and_survives() -> None:
    prop = _property()
    feature = _feature()
    unrelated_manual = _feature()
    # Same feature is both manually linked AND implied by a room attribute.
    PropertyFeature.objects.create(property=prop, feature=feature, sort_order=0)
    PropertyFeature.objects.create(property=prop, feature=unrelated_manual, sort_order=1)
    _assign(_room(prop), implies=feature)

    recompute_derived_features(prop)

    # The manually-linked-and-implied feature is neither duplicated nor demoted.
    both = PropertyFeature.objects.filter(property=prop, feature=feature)
    assert both.count() == 1
    assert both.get().is_derived is False
    # The unrelated manual feature is untouched (not deleted by the recompute).
    assert PropertyFeature.objects.filter(
        property=prop, feature=unrelated_manual, is_derived=False
    ).exists()


def test_union_across_rooms_dedupes_and_tracks_last_implier() -> None:
    prop = _property()
    feature = _feature()
    room_a = _room(prop)
    room_b = _room(prop)
    _assign(room_a, implies=feature)
    _assign(room_b, implies=feature)

    recompute_derived_features(prop)
    # Two rooms imply the same feature → exactly one derived link.
    assert PropertyFeature.objects.filter(property=prop, feature=feature).count() == 1

    # Deleting one room still leaves the other implying it → link survives.
    room_a.delete()
    recompute_derived_features(prop)
    assert PropertyFeature.objects.filter(property=prop, feature=feature).exists()

    # Deleting the last implier drops it.
    room_b.delete()
    recompute_derived_features(prop)
    assert not PropertyFeature.objects.filter(property=prop, feature=feature).exists()
