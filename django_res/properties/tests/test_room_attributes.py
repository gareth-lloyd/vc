"""GAP-064 — Room facet columns + admin-editable RoomAttribute catalog."""

from __future__ import annotations

from typing import cast

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from properties.enums import EnsuiteType, RoomAccess
from properties.factories import FeatureFactory, RoomAttributeFactory, RoomFactory
from properties.models import Feature, Room, RoomAttribute, RoomAttributeAssignment

pytestmark = pytest.mark.django_db


def make_room(**kwargs: object) -> Room:
    return cast(Room, RoomFactory(**kwargs))


def make_attribute(**kwargs: object) -> RoomAttribute:
    return cast(RoomAttribute, RoomAttributeFactory(**kwargs))


class TestFacetColumns:
    def test_facets_default_to_blank_unknown(self) -> None:
        room = make_room()
        assert room.ensuite_type == ""
        assert room.access == ""

    def test_ensuite_type_choices(self) -> None:
        assert set(EnsuiteType.values) == {"shower", "bath", "both"}

    def test_access_choices(self) -> None:
        assert set(RoomAccess.values) == {"inside", "outside"}

    def test_facets_are_settable(self) -> None:
        room = make_room(
            ensuite_type=EnsuiteType.SHOWER,
            access=RoomAccess.OUTSIDE,
            is_ensuite=True,
        )
        room.refresh_from_db()
        assert room.ensuite_type == EnsuiteType.SHOWER
        assert room.access == RoomAccess.OUTSIDE

    def test_ensuite_type_requires_is_ensuite(self) -> None:
        # `ensuite_type` refines `is_ensuite` — a typed room that claims not to
        # be ensuite is incoherent, and loaders/admin bypass the serializer, so
        # the DB enforces it.
        with pytest.raises(IntegrityError):
            make_room(ensuite_type=EnsuiteType.BATH, is_ensuite=False)

    def test_blank_ensuite_type_allowed_either_way(self) -> None:
        make_room(ensuite_type="", is_ensuite=False)
        make_room(ensuite_type="", is_ensuite=True)


class TestRoomAttributeCatalog:
    def test_slug_is_unique(self) -> None:
        make_attribute(slug="aircon-test")
        with pytest.raises(IntegrityError):
            RoomAttribute.objects.create(name="Duplicate", slug="aircon-test")

    def test_ordering_by_sort_order_then_name(self) -> None:
        b = make_attribute(name="B attr", sort_order=1)
        a = make_attribute(name="A attr", sort_order=2)
        first = make_attribute(name="Z attr", sort_order=0)
        assert list(RoomAttribute.objects.filter(pk__in=[a.pk, b.pk, first.pk])) == [
            first,
            b,
            a,
        ]

    def test_implies_property_feature_set_null_on_feature_delete(self) -> None:
        feature = cast(Feature, FeatureFactory())
        attr = make_attribute(implies_property_feature=feature)
        feature.delete()
        attr.refresh_from_db()
        assert attr.implies_property_feature is None


class TestRoomAttributeAssignment:
    def test_unique_per_room_and_attribute(self) -> None:
        room = make_room()
        attr = make_attribute()
        RoomAttributeAssignment.objects.create(room=room, attribute=attr)
        with pytest.raises(IntegrityError):
            RoomAttributeAssignment.objects.create(room=room, attribute=attr)

    def test_in_use_attribute_cannot_be_deleted(self) -> None:
        room = make_room()
        attr = make_attribute()
        RoomAttributeAssignment.objects.create(room=room, attribute=attr)
        with pytest.raises(ProtectedError):
            attr.delete()

    def test_unused_attribute_can_be_deleted(self) -> None:
        attr = make_attribute()
        attr.delete()
        assert not RoomAttribute.objects.filter(pk=attr.pk).exists()

    def test_deleting_room_cascades_assignments(self) -> None:
        room = make_room()
        attr = make_attribute()
        RoomAttributeAssignment.objects.create(room=room, attribute=attr, note="sea view")
        room.delete()
        assert not RoomAttributeAssignment.objects.filter(attribute=attr).exists()
        # The catalog row survives its assignments.
        assert RoomAttribute.objects.filter(pk=attr.pk).exists()

    def test_assignments_reachable_via_room_attribute_links(self) -> None:
        room = make_room()
        attr = make_attribute()
        link = RoomAttributeAssignment.objects.create(room=room, attribute=attr)
        assert list(room.attribute_links.all()) == [link]


class TestFactory:
    def test_room_attribute_factory_reuses_row_by_slug(self) -> None:
        a = make_attribute(slug="reused-slug")
        with transaction.atomic():
            b = make_attribute(slug="reused-slug")
        assert a.pk == b.pk
