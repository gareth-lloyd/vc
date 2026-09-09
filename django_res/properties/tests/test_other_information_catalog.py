"""`properties.other_information_catalog` — the GAP-091 tag vocabulary.

The catalog is a dev-seed convenience, NOT a migration: prod/staging get the
same rows from the legacy feature loaders, so slugs and `legacy_id`s must
match what `FeatureCategoryLoader` / `FeatureLoader` would write, and the
sync must adopt loader-written rows by `legacy_id` rather than mint twins.
"""

from __future__ import annotations

from typing import cast

import pytest

from properties.enums import FeatureServiceType
from properties.factories import FeatureCategoryFactory, FeatureFactory
from properties.models import Feature, FeatureCategory
from properties.other_information_catalog import (
    OTHER_INFORMATION_CATEGORY_SLUG,
    STARTER_TAGS,
    sync_other_information_tags,
    tag_slug,
)

pytestmark = pytest.mark.django_db


def test_sync_creates_category_and_every_tag() -> None:
    created = sync_other_information_tags()

    assert OTHER_INFORMATION_CATEGORY_SLUG == "other-information"
    category = FeatureCategory.objects.get(slug=OTHER_INFORMATION_CATEGORY_SLUG)
    assert category.name == "Other Information"
    assert category.legacy_id == "8"
    assert category.sort_order == 60
    assert category.icon

    tags = {f.slug: f for f in Feature.objects.filter(category=category)}
    assert set(tags) == {tag_slug(name) for name, *_ in STARTER_TAGS}
    assert created == len(STARTER_TAGS)
    assert len(STARTER_TAGS) == 11
    for index, (name, legacy_id, _icon) in enumerate(STARTER_TAGS):
        tag = tags[tag_slug(name)]
        assert tag.name == name
        assert tag.legacy_id == legacy_id
        assert tag.sort_order == index
        assert tag.is_active
        assert tag.icon
        assert tag.service_type == FeatureServiceType.AMENITY
    assert tags["pets-allowed"].legacy_id == "128"


def test_sync_is_idempotent() -> None:
    sync_other_information_tags()
    before = Feature.objects.count()

    assert sync_other_information_tags() == 0
    assert Feature.objects.count() == before
    assert FeatureCategory.objects.filter(slug=OTHER_INFORMATION_CATEGORY_SLUG).count() == 1


def test_sync_leaves_a_same_slug_feature_in_another_category_alone() -> None:
    outdoor = cast(FeatureCategory, FeatureCategoryFactory(slug="outdoor", name="Outdoor"))
    existing = cast(
        Feature, FeatureFactory(slug="fenced-pool", name="Fenced pool (outdoor)", category=outdoor)
    )

    created = sync_other_information_tags()

    existing.refresh_from_db()
    assert existing.category == outdoor
    assert existing.legacy_id is None
    assert created == len(STARTER_TAGS) - 1
    assert Feature.objects.filter(slug="fenced-pool").count() == 1


def test_sync_adopts_loader_rows_by_legacy_id_when_the_slug_has_drifted() -> None:
    # A loader-first DB where a curator later renamed the category and one
    # tag: slugs no longer match the catalog, legacy ids still do. The
    # category name is unique, so a slug-keyed create would also collide.
    category = cast(
        FeatureCategory,
        FeatureCategoryFactory(slug="other-info", name="Other Information", legacy_id="8"),
    )
    renamed = cast(
        Feature,
        FeatureFactory(
            slug="pets-welcome", name="Pets welcome", legacy_id="128", category=category
        ),
    )

    created = sync_other_information_tags()

    assert created == len(STARTER_TAGS) - 1
    assert FeatureCategory.objects.count() == 1
    assert not Feature.objects.filter(slug="pets-allowed").exists()
    renamed.refresh_from_db()
    assert (renamed.slug, renamed.name, renamed.category_id) == (
        "pets-welcome",
        "Pets welcome",
        category.pk,
    )
    assert Feature.objects.filter(category=category).count() == len(STARTER_TAGS)
