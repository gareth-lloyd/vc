from __future__ import annotations

from datetime import datetime
from typing import cast

import pytest
import structlog

from data_migration.base import LoadReport
from data_migration.loaders.property_children import (
    PropertyFeatureMappingLoader,
    PropertyImageLoader,
    RoomLoader,
)
from properties.factories import FeatureFactory, PropertyFactory
from properties.models.features import Feature
from properties.models.property import Property
from properties.models.rooms import Room


def _row(
    *,
    FeatureId: object,
    VillaId: object,
    MappingOrder: object,
    FeatureName: object = "Feature",
    FeatureDeletedAt: object = None,
) -> dict[str, object]:
    return {
        "FeatureId": FeatureId,
        "VillaId": VillaId,
        "MappingOrder": MappingOrder,
        "FeatureName": FeatureName,
        "FeatureDeletedAt": FeatureDeletedAt,
    }


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
    """Duplicate pairs collapse to one link carrying the lowest MappingOrder
    (BUG-030 §11: the Python dedupe mirrors the query's `MIN(MappingOrder)`
    so a remapped twin can never violate the unique constraint)."""
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
    assert links.get().sort_order == 2


@pytest.mark.django_db
def test_load_rows_missing_legacy_id_is_skipped() -> None:
    PropertyFactory(legacy_id="500")  # feature deliberately absent
    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")

    loader._load_rows([_row(FeatureId="999", VillaId="500", MappingOrder=1)], report)

    assert (report.created, report.updated, report.skipped) == (0, 0, 1)
    assert Property.features.through.objects.count() == 0


# --- BUG-030 §11: deleted features remap to their live namesake ---

_DELETED = datetime(2024, 5, 28, 12, 0)


def _feature_remap_setup() -> tuple[Property, Feature]:
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    twin = cast(Feature, FeatureFactory(legacy_id="299", name="Sitting room"))
    return prop, twin


@pytest.mark.django_db
def test_deleted_feature_with_a_live_namesake_lands_on_the_twin() -> None:
    prop, twin = _feature_remap_setup()
    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")

    loader._load_rows(
        [
            _row(
                FeatureId="55",
                VillaId="500",
                MappingOrder=4,
                FeatureName="  sitting ROOM ",
                FeatureDeletedAt=_DELETED,
            )
        ],
        report,
    )

    assert (report.created, report.skipped) == (1, 0)
    link = Property.features.through.objects.get(property_id=prop.pk)
    assert link.feature_id == twin.pk
    assert link.sort_order == 4


@pytest.mark.django_db
def test_villa_carrying_both_the_deleted_and_the_live_feature_gets_one_link() -> None:
    prop, twin = _feature_remap_setup()
    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")

    loader._load_rows(
        [
            _row(FeatureId="299", VillaId="500", MappingOrder=9, FeatureName="Sitting room"),
            _row(
                FeatureId="55",
                VillaId="500",
                MappingOrder=3,
                FeatureName="Sitting room",
                FeatureDeletedAt=_DELETED,
            ),
        ],
        report,
    )

    assert report.errors == []
    links = Property.features.through.objects.filter(property_id=prop.pk)
    assert links.count() == 1
    assert links.get().feature_id == twin.pk
    assert links.get().sort_order == 3


@pytest.mark.django_db
def test_two_live_namesakes_resolve_to_the_lowest_legacy_id() -> None:
    prop, low = _feature_remap_setup()  # legacy_id 299
    FeatureFactory(legacy_id="1001", name="Sitting Room")
    loader = PropertyFeatureMappingLoader()

    loader._load_rows(
        [
            _row(
                FeatureId="55",
                VillaId="500",
                MappingOrder=1,
                FeatureName="Sitting room",
                FeatureDeletedAt=_DELETED,
            )
        ],
        LoadReport(loader="property_feature"),
    )

    link = Property.features.through.objects.get(property_id=prop.pk)
    assert link.feature_id == low.pk


@pytest.mark.django_db
def test_deleted_feature_without_a_twin_is_skipped_and_logged() -> None:
    PropertyFactory(legacy_id="500")
    loader = PropertyFeatureMappingLoader()
    report = LoadReport(loader="property_feature")

    with structlog.testing.capture_logs() as logs:
        loader._load_rows(
            [
                _row(
                    FeatureId="77",
                    VillaId="500",
                    MappingOrder=1,
                    FeatureName="Helipad",
                    FeatureDeletedAt=_DELETED,
                )
            ],
            report,
        )

    assert (report.created, report.skipped) == (0, 1)
    assert Property.features.through.objects.count() == 0
    assert any(
        log["event"] == "data_migration.deleted_feature_unmapped"
        and log["feature_id"] == "77"
        and log["feature_name"] == "Helipad"
        for log in logs
    )


def test_mapping_query_carries_the_feature_name_and_deletion() -> None:
    query = PropertyFeatureMappingLoader.legacy_query
    assert "f.Name AS FeatureName" in query
    assert "f.DeletedAt AS FeatureDeletedAt" in query
    assert "MIN(m.MappingOrder) AS MappingOrder" in query
    assert "DeletedAt IS NULL" not in query  # deleted features are remapped, not filtered
    assert "LEFT JOIN VillaFeatures f" in query  # orphan FeatureIds still reach the skip path


@pytest.mark.django_db
def test_mapping_on_a_feature_id_with_no_legacy_row_is_skipped() -> None:
    PropertyFactory(legacy_id="500")
    report = LoadReport(loader="property_feature")
    PropertyFeatureMappingLoader()._load_rows(
        [_row(FeatureId="9999", VillaId="500", MappingOrder=1, FeatureName=None)], report
    )
    assert (report.created, report.skipped) == (0, 1)


@pytest.mark.django_db
def test_long_deleted_feature_name_matches_its_truncated_loaded_twin() -> None:
    long_name = "Sitting room " * 12  # > 128 chars; FeatureLoader stores name[:128]
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    twin = cast(Feature, FeatureFactory(legacy_id="299", name=long_name.strip()[:128]))
    PropertyFeatureMappingLoader()._load_rows(
        [
            _row(
                FeatureId="55",
                VillaId="500",
                MappingOrder=1,
                FeatureName=long_name,
                FeatureDeletedAt=_DELETED,
            )
        ],
        LoadReport(loader="property_feature"),
    )
    assert Property.features.through.objects.get(property_id=prop.pk).feature_id == twin.pk


@pytest.mark.django_db
def test_legacy_link_promotes_a_derived_row_to_manual() -> None:
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    feature = cast(Feature, FeatureFactory(legacy_id="42"))
    through = Property.features.through
    through.objects.create(property=prop, feature=feature, is_derived=True)
    report = LoadReport(loader="property_feature")
    PropertyFeatureMappingLoader()._load_rows(
        [_row(FeatureId="42", VillaId="500", MappingOrder=2)], report
    )
    assert report.updated == 1
    assert through.objects.get(property_id=prop.pk, feature_id=feature.pk).is_derived is False


def _image_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Id": 1,
        "VillaId": "500",
        "Name": "img.jpg",
        "Description": None,
        "IsGallary": 1,
        "IsHero": 0,
        "IsInterior1": 0,
        "IsInterior2": 0,
        "IsExterior1": 0,
        "IsExterior2": 0,
        "SortOrder": 0,
        "IsActive": 1,
        "SlotInterior1": None,
        "SlotInterior2": None,
        "SlotExterior1": None,
        "SlotExterior2": None,
    }
    row.update(overrides)
    return row


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("flag", "slot"),
    [
        ("IsInterior1", "SlotInterior1"),
        ("IsInterior2", "SlotInterior2"),
        ("IsExterior1", "SlotExterior1"),
        ("IsExterior2", "SlotExterior2"),
    ],
)
def test_image_flagged_blank_description_gains_slot_caption(flag: str, slot: str) -> None:
    PropertyFactory(legacy_id="500")
    row = _image_row(**{flag: 1, slot: "  A lovely view  "})

    kwargs = PropertyImageLoader().transform(row)

    assert kwargs is not None
    assert kwargs["description"] == "A lovely view"


@pytest.mark.django_db
def test_image_own_description_wins_over_slot_caption() -> None:
    PropertyFactory(legacy_id="500")
    row = _image_row(IsInterior1=1, Description="Own words", SlotInterior1="Slot words")

    kwargs = PropertyImageLoader().transform(row)

    assert kwargs is not None
    assert kwargs["description"] == "Own words"


@pytest.mark.django_db
def test_image_multi_flag_takes_first_flagged_slot_with_text() -> None:
    PropertyFactory(legacy_id="500")
    row = _image_row(
        IsInterior1=1,
        IsExterior1=1,
        SlotInterior1="Interior text",
        SlotExterior1="Exterior text",
    )

    kwargs = PropertyImageLoader().transform(row)

    assert kwargs is not None
    assert kwargs["description"] == "Interior text"


@pytest.mark.django_db
def test_image_multi_flag_falls_through_blank_slot() -> None:
    PropertyFactory(legacy_id="500")
    row = _image_row(
        IsInterior1=1,
        IsExterior1=1,
        SlotInterior1="  ",
        SlotExterior1="Exterior text",
    )

    kwargs = PropertyImageLoader().transform(row)

    assert kwargs is not None
    assert kwargs["description"] == "Exterior text"


@pytest.mark.django_db
def test_image_flagged_without_slot_text_stays_blank() -> None:
    PropertyFactory(legacy_id="500")
    row = _image_row(IsInterior2=1)

    kwargs = PropertyImageLoader().transform(row)

    assert kwargs is not None
    assert kwargs["description"] == ""


@pytest.mark.django_db
def test_image_unflagged_ignores_slot_text() -> None:
    """Slot text pairs only with its flagged image — a plain gallery image
    from the same villa must not inherit the villa-level caption."""
    PropertyFactory(legacy_id="500")
    row = _image_row(SlotInterior1="Interior text", SlotExterior1="Exterior text")

    kwargs = PropertyImageLoader().transform(row)

    assert kwargs is not None
    assert kwargs["description"] == ""
