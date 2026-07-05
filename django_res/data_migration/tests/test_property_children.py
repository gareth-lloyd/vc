from __future__ import annotations

from typing import cast

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.property_children import PropertyFeatureMappingLoader, RoomLoader
from properties.factories import FeatureFactory, PropertyFactory
from properties.models.features import Feature
from properties.models.property import Property
from properties.models.rooms import Room


def _row(*, FeatureId: object, VillaId: object, MappingOrder: object) -> dict[str, object]:
    return {"FeatureId": FeatureId, "VillaId": VillaId, "MappingOrder": MappingOrder}


def _room_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Id": 1,
        "VillaId": "500",
        "Name": "Master Suite",
        "WebsiteDescription": "",
        "VCNotes": "",
        "IsEnsuit": 0,
        "SortOrder": 0,
        "BedDouble": 1,
        "BedTwinDouble": 0,
        "BedTwin": 0,
        "BedSingle": 0,
        "BedBunk": 0,
        "BedSofa": 0,
        "BedChildrens": 0,
        "PlacementName": None,
    }
    row.update(overrides)
    return row


@pytest.mark.django_db
class TestRoomLoaderPlacement:
    """GAP-065 — the loader reads the joined `VillaRoomsPlacement.Name`,
    preserves it verbatim in `placement_note` and parses the two axes."""

    def test_placement_name_is_preserved_and_parsed(self) -> None:
        PropertyFactory(legacy_id="500")
        report = LoadReport(loader="room")
        RoomLoader()._load_rows(
            [_room_row(PlacementName="  First floor of the guest house ")], report
        )

        assert report.errors == []
        room = Room.objects.get(legacy_id="1")
        assert room.placement_note == "First floor of the guest house"
        assert room.placement == "guest_house"
        assert room.floor == "first"

    def test_bare_floor_implies_main_house(self) -> None:
        PropertyFactory(legacy_id="500")
        RoomLoader()._load_rows([_room_row(PlacementName="First foor")], LoadReport(loader="room"))
        room = Room.objects.get(legacy_id="1")
        assert room.placement == "main_house"
        assert room.floor == "first"

    def test_null_placement_loads_room_with_all_location_blank(self) -> None:
        # No more hardcoded MAIN_HOUSE: unknown stays honestly unknown.
        PropertyFactory(legacy_id="500")
        report = LoadReport(loader="room")
        RoomLoader()._load_rows([_room_row(PlacementName=None)], report)

        assert report.created == 1
        room = Room.objects.get(legacy_id="1")
        assert room.placement == ""
        assert room.floor == ""
        assert room.placement_note == ""

    def test_unparseable_placement_survives_in_note_only(self) -> None:
        PropertyFactory(legacy_id="500")
        RoomLoader()._load_rows([_room_row(PlacementName="Upper level")], LoadReport(loader="room"))
        room = Room.objects.get(legacy_id="1")
        assert room.placement == ""
        assert room.floor == ""
        assert room.placement_note == "Upper level"  # the no-loss guarantee

    def test_rerun_is_idempotent(self) -> None:
        PropertyFactory(legacy_id="500")
        loader = RoomLoader()
        first = LoadReport(loader="room")
        loader._load_rows([_room_row(PlacementName="Ground floor")], first)
        second = LoadReport(loader="room")
        loader._load_rows([_room_row(PlacementName="Ground floor")], second)

        assert (first.created, first.updated) == (1, 0)
        assert (second.created, second.updated) == (0, 1)
        assert Room.objects.filter(legacy_id="1").count() == 1

    def test_since_clause_is_alias_qualified(self) -> None:
        # `loadlegacy --since` appends a WHERE via `_apply_since`; with the
        # placement JOIN in the FROM, an unqualified `UpdatedAt` would be
        # ambiguous SQL. The dict-row tests never execute SQL, so pin the
        # generated query text itself.
        loader = RoomLoader(since="2026-01-01T00:00:00")
        sql = loader._apply_since(loader.legacy_query)
        assert sql.endswith("WHERE r.UpdatedAt > '2026-01-01T00:00:00'")
        assert " UpdatedAt >" not in sql.replace("r.UpdatedAt", "")


@pytest.mark.django_db
def test_load_rows_persists_sort_order_from_mapping_order() -> None:
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    feature = cast(Feature, FeatureFactory(legacy_id="42"))

    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")
    loader._load_rows([_row(FeatureId="42", VillaId="500", MappingOrder=3)], report)

    assert (report.created, report.updated, report.skipped) == (1, 0, 0)
    through = Property.features.through
    link = through.objects.get(property_id=prop.pk, feature_id=feature.pk)
    assert link.sort_order == 3


@pytest.mark.django_db
def test_load_rows_mapping_order_zero_is_kept() -> None:
    """A legitimate MappingOrder of 0 must persist as 0 (no falsy-zero bug)."""
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    feature = cast(Feature, FeatureFactory(legacy_id="42"))

    loader = PropertyFeatureMappingLoader()
    loader._load_rows(
        [_row(FeatureId="42", VillaId="500", MappingOrder=0)],
        LoadReport(loader="property_feature"),
    )

    through = Property.features.through
    assert through.objects.get(property_id=prop.pk, feature_id=feature.pk).sort_order == 0


@pytest.mark.django_db
def test_load_rows_rerun_updates_sort_order_and_reports_updated() -> None:
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    feature = cast(Feature, FeatureFactory(legacy_id="42"))
    through = Property.features.through
    loader = PropertyFeatureMappingLoader()

    first = LoadReport(loader="property_feature")
    loader._load_rows([_row(FeatureId="42", VillaId="500", MappingOrder=1)], first)
    assert (first.created, first.updated) == (1, 0)

    second = LoadReport(loader="property_feature")
    loader._load_rows([_row(FeatureId="42", VillaId="500", MappingOrder=5)], second)
    assert (second.created, second.updated) == (0, 1)
    assert through.objects.get(property_id=prop.pk, feature_id=feature.pk).sort_order == 5
    assert through.objects.filter(property_id=prop.pk, feature_id=feature.pk).count() == 1


@pytest.mark.django_db
def test_load_rows_duplicate_pair_collapses_to_one_row() -> None:
    """The `update_or_create` backstop: if the in-SQL MIN dedup ever lets a
    duplicate pair through, the second row updates the first instead of
    violating the unique constraint."""
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    feature = cast(Feature, FeatureFactory(legacy_id="42"))
    through = Property.features.through
    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")

    loader._load_rows(
        [
            _row(FeatureId="42", VillaId="500", MappingOrder=2),
            _row(FeatureId="42", VillaId="500", MappingOrder=7),
        ],
        report,
    )

    assert report.errors == []
    links = through.objects.filter(property_id=prop.pk, feature_id=feature.pk)
    assert links.count() == 1
    assert links.get().sort_order == 7


@pytest.mark.django_db
def test_load_rows_missing_legacy_id_is_skipped() -> None:
    PropertyFactory(legacy_id="500")  # feature deliberately absent
    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")

    loader._load_rows([_row(FeatureId="999", VillaId="500", MappingOrder=1)], report)

    assert (report.created, report.updated, report.skipped) == (0, 0, 1)
    assert Property.features.through.objects.count() == 0
