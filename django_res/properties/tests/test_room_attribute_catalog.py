"""GAP-064 — starter RoomAttribute catalog seed + `sync_room_attributes()`.

The migration (0027) seeds the catalog by calling the live function, so the
function is tested directly here; the migration test just pins that the rows
exist after `migrate`.
"""

from __future__ import annotations

from typing import cast

import pytest

from properties.factories import FeatureFactory
from properties.models import Feature, RoomAttribute
from properties.room_attribute_catalog import (
    STARTER_ATTRIBUTES,
    starter_slugs,
    sync_room_attributes,
)

pytestmark = pytest.mark.django_db


class TestMigrationSeed:
    def test_starter_rows_exist_after_migrate(self) -> None:
        rows = RoomAttribute.objects.filter(slug__in=starter_slugs())
        assert rows.count() == len(STARTER_ATTRIBUTES)
        assert all(row.is_active for row in rows)

    def test_expected_slugs(self) -> None:
        assert starter_slugs() == {
            "aircon",
            "ceiling_fan",
            "sea_view",
            "balcony",
            "terrace",
            "wheelchair",
            "in_room_safe",
            "hairdryer",
            "mini_fridge",
        }


class TestSyncRoomAttributes:
    def test_idempotent(self) -> None:
        before = RoomAttribute.objects.count()
        sync_room_attributes()
        sync_room_attributes()
        assert RoomAttribute.objects.count() == before

    def test_never_clobbers_curator_edits(self) -> None:
        attr = RoomAttribute.objects.get(slug="aircon")
        attr.name = "Climate control"
        attr.sort_order = 99
        attr.save()
        sync_room_attributes()
        attr.refresh_from_db()
        assert attr.name == "Climate control"
        assert attr.sort_order == 99

    def test_implication_links_when_candidate_feature_exists(self) -> None:
        # Features are NOT migration-seeded, so at migrate time implications
        # stay NULL; a re-invocation links them once Features exist (set-if-NULL).
        feature = cast(Feature, FeatureFactory(slug="sea-view"))
        assert RoomAttribute.objects.get(slug="sea_view").implies_property_feature is None
        sync_room_attributes()
        attr = RoomAttribute.objects.get(slug="sea_view")
        assert attr.implies_property_feature == feature

    def test_implication_never_clobbers_a_curator_link(self) -> None:
        FeatureFactory(slug="sea-view")
        curator_choice = cast(Feature, FeatureFactory(slug="panoramic-views"))
        attr = RoomAttribute.objects.get(slug="sea_view")
        attr.implies_property_feature = curator_choice
        attr.save()
        sync_room_attributes()
        attr.refresh_from_db()
        assert attr.implies_property_feature == curator_choice

    def test_implication_noop_when_no_candidate_feature(self) -> None:
        sync_room_attributes()
        attr = RoomAttribute.objects.get(slug="wheelchair")
        assert attr.implies_property_feature is None

    def test_recreates_a_deleted_starter_row(self) -> None:
        RoomAttribute.objects.get(slug="hairdryer").delete()
        sync_room_attributes()
        assert RoomAttribute.objects.filter(slug="hairdryer").exists()
