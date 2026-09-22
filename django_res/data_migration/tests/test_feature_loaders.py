"""`FeatureCategoryLoader` / `FeatureLoader` converge with the GAP-091 catalog.

Prod is loader-first; dev DBs are catalog-first (`seed_dev`). Both orders
must land on ONE `other-information` category and one row per tag: the
catalog stamps the legacy ids the loaders upsert on and derives slugs the
loaders' way, so a loader run over a seeded DB updates in place instead of
tripping the unique slug constraint.
"""

from __future__ import annotations

from typing import Any

import pytest

from data_migration.base import LoadReport
from data_migration.loaders.lookups import FeatureCategoryLoader, FeatureLoader
from properties.enums import FeatureServiceType
from properties.models import Feature, FeatureCategory
from properties.other_information_catalog import (
    OTHER_INFORMATION_CATEGORY_SLUG,
    STARTER_TAGS,
    sync_other_information_tags,
    tag_slug,
)

pytestmark = pytest.mark.django_db

_CATEGORY_ROW = {"Id": 8, "Name": "Other Information", "IsActive": True, "Code": 60}


def _tag_row(
    name: str, legacy_id: str, order: int, *, category_code: int | None = 60
) -> dict[str, Any]:
    # The real `FeatureLoader` row shape: `CategoryId` is the category's Id
    # and `CategoryCode` its `Code` (BUG-030 §12). Legacy `ServiceType` is
    # not selected any more (every live feature stores 20).
    return {
        "Id": int(legacy_id),
        "Name": name,
        "Description": None,
        "FeatureOrder": order,
        "CategoryId": 8,
        "CategoryCode": category_code,
    }


def _load_category() -> LoadReport:
    loader = FeatureCategoryLoader()
    report = LoadReport(loader=loader.name)
    loader._process_row(_CATEGORY_ROW, report)
    return report


def _load_tag(row: dict[str, Any]) -> LoadReport:
    loader = FeatureLoader()
    report = LoadReport(loader=loader.name)
    loader._process_row(row, report)
    return report


@pytest.mark.parametrize(
    ("name", "legacy_id"),
    [(name, legacy_id) for name, legacy_id, _icon in STARTER_TAGS],
    ids=[legacy_id for _name, legacy_id, _icon in STARTER_TAGS],
)
def test_loader_after_catalog_updates_in_place(name: str, legacy_id: str) -> None:
    sync_other_information_tags()
    categories_before = FeatureCategory.objects.count()
    features_before = Feature.objects.count()

    cat_report = _load_category()
    tag_report = _load_tag(_tag_row(name, legacy_id, order=3))

    assert cat_report.errors == [] and cat_report.updated == 1 and cat_report.created == 0
    assert tag_report.errors == [] and tag_report.updated == 1 and tag_report.created == 0
    assert FeatureCategory.objects.count() == categories_before
    assert Feature.objects.count() == features_before
    tag = Feature.objects.get(slug=tag_slug(name))
    assert tag.category.slug == OTHER_INFORMATION_CATEGORY_SLUG
    assert tag.legacy_id == legacy_id
    assert tag.sort_order == 3  # the loader's value won


def test_catalog_after_loader_creates_nothing_for_loaded_rows() -> None:
    assert _load_category().created == 1
    assert _load_tag(_tag_row("No smoking indoors", "125", order=3)).created == 1

    created = sync_other_information_tags()

    # Everything except the one tag the loader already wrote.
    assert created == len(STARTER_TAGS) - 1
    assert FeatureCategory.objects.filter(slug=OTHER_INFORMATION_CATEGORY_SLUG).count() == 1
    assert Feature.objects.filter(slug="no-smoking-indoors").count() == 1


def test_catalog_after_renamed_loader_row_creates_nothing_for_it() -> None:
    # A loader-first row whose name changed since the Dec-2024 snapshot: the
    # slug drifts but the legacy id is the join key, so no twin is minted.
    assert _load_category().created == 1
    assert _load_tag(_tag_row("No smoking anywhere indoors", "125", order=3)).created == 1

    created = sync_other_information_tags()

    assert created == len(STARTER_TAGS) - 1
    assert not Feature.objects.filter(slug="no-smoking-indoors").exists()
    assert Feature.objects.filter(legacy_id="125").count() == 1


# --- BUG-030 §12: service_type derives from the category Code ---


@pytest.mark.parametrize(
    ("category_code", "expected"),
    [
        (50, FeatureServiceType.INCLUDED_SERVICE),  # "Included Features"
        (70, FeatureServiceType.PAID_ADDON),  # "Services On Request"
        (60, FeatureServiceType.AMENITY),
        (None, FeatureServiceType.AMENITY),
    ],
)
def test_service_type_derives_from_the_category_code(
    category_code: int | None, expected: FeatureServiceType
) -> None:
    _load_category()
    kwargs = FeatureLoader().transform(
        _tag_row("Pool towels", "300", 1, category_code=category_code)
    )
    assert kwargs is not None
    assert kwargs["service_type"] == expected


def test_feature_query_selects_the_category_code_not_service_type() -> None:
    query = FeatureLoader.legacy_query
    # Both columns come from ONE first-mapping subquery, deterministically.
    assert "OUTER APPLY (SELECT TOP 1 c.Id, c.Code" in query
    assert "ORDER BY m.Id, c.Id) cat" in query
    assert "cat.Id AS CategoryId, cat.Code AS CategoryCode" in query
    assert query.endswith("ORDER BY f.Id")
    assert "ServiceType" not in query
    assert not hasattr(FeatureLoader, "_service_type_map")


# --- The category slug is pinned: every reader keys on it ---


def test_category_slug_is_pinned_regardless_of_legacy_name() -> None:
    # The live legacy row was renamed to "Other Information Tags" after the
    # checked-in snapshot; slugifying that emptied the Features tab's block,
    # the Zoho partition and the seeding stage. Name follows legacy, slug does
    # not.
    loader = FeatureCategoryLoader()
    report = LoadReport(loader=loader.name)
    loader._process_row({**_CATEGORY_ROW, "Name": "Other Information Tags"}, report)

    assert report.errors == [] and report.created == 1
    category = FeatureCategory.objects.get(legacy_id="8")
    assert category.name == "Other Information Tags"
    assert category.slug == OTHER_INFORMATION_CATEGORY_SLUG


def test_other_category_slugs_still_follow_the_name() -> None:
    loader = FeatureCategoryLoader()
    report = LoadReport(loader=loader.name)
    loader._process_row({"Id": 1, "Name": "Living Spaces", "IsActive": True, "Code": 20}, report)

    assert report.errors == []
    assert FeatureCategory.objects.get(legacy_id="1").slug == "living-spaces"
