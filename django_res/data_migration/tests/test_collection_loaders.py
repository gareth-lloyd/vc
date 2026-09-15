"""`CollectionLoader` / `CollectionMembershipLoader` (BUG-030 §13)."""

from __future__ import annotations

from typing import cast

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.properties import CollectionLoader, CollectionMembershipLoader
from properties.factories import CollectionFactory, PropertyFactory
from properties.models.features import Collection, CollectionMembership
from properties.models.property import Property

pytestmark = pytest.mark.django_db


def test_collection_transform() -> None:
    kwargs = CollectionLoader().transform(
        {"Id": 66, "Name": "  Chef Included ", "Description": " Private chef. "}
    )
    assert kwargs == {
        "name": "Chef Included",
        "slug": "chef-included-66",
        "description": "Private chef.",
        "is_active": True,
    }


def test_collection_blank_name_is_skipped() -> None:
    assert CollectionLoader().transform({"Id": 1, "Name": " ", "Description": ""}) is None


def test_collection_query_selects_only_live_collections_with_no_fake_column() -> None:
    query = CollectionLoader.legacy_query
    assert "WHERE DeletedAt IS NULL" in query
    assert "IsActive" not in query  # every loaded collection is active


def _membership_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Id": 1,
        "VillaMasterId": "500",
        "VillaCollectionId": "66",
        "VillaOrder": 3,
        "Description": " Featured ",
    }
    row.update(overrides)
    return row


def test_membership_transform_resolves_both_sides() -> None:
    prop = cast(Property, PropertyFactory(legacy_id="500"))
    coll = cast(Collection, CollectionFactory(legacy_id="66"))
    kwargs = CollectionMembershipLoader().transform(_membership_row())
    assert kwargs == {
        "property": prop,
        "collection": coll,
        "sort_order": 3,
        "description": "Featured",
    }


def test_membership_on_a_deleted_collection_or_villa_is_skipped() -> None:
    PropertyFactory(legacy_id="500")
    assert CollectionMembershipLoader().transform(_membership_row()) is None  # no collection
    CollectionFactory(legacy_id="66")
    assert CollectionMembershipLoader().transform(_membership_row(VillaMasterId="999")) is None


def test_duplicate_membership_keeps_the_first_row() -> None:
    PropertyFactory(legacy_id="500")
    CollectionFactory(legacy_id="66")
    loader = CollectionMembershipLoader()
    report = LoadReport(loader=loader.name)
    loader._load_rows(
        [_membership_row(Id=1, VillaOrder=1), _membership_row(Id=2, VillaOrder=5)], report
    )
    assert (report.created, report.skipped) == (1, 1)
    assert CollectionMembership.objects.get().sort_order == 1
