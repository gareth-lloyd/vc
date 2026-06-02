"""Feature/category icons are seeded and backfilled.

Covers two paths that put lucide icon names on the catalogue:
- the dev-seed stage (`_ensure_catalogue`), and
- the idempotent `properties.0012` slug->icon backfill migration.
"""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as global_apps

from properties.models.features import Feature, FeatureCategory
from seeding.stages.features import _ensure_catalogue

# Migration module name starts with a digit, so import it dynamically.
_0012 = importlib.import_module("properties.migrations.0012_backfill_feature_icons")


@pytest.mark.django_db
def test_seed_catalogue_assigns_icons() -> None:
    _ensure_catalogue()

    assert FeatureCategory.objects.exists()
    assert Feature.objects.exists()
    assert not FeatureCategory.objects.filter(icon="").exists(), (
        "every seeded category should carry an icon name"
    )
    assert not Feature.objects.filter(icon="").exists(), (
        "every seeded feature should carry an icon name"
    )
    # Spot-check a couple of the curated mappings.
    assert Feature.objects.get(slug="wifi").icon == "wifi"
    assert Feature.objects.get(slug="pool").icon == "waves"


@pytest.mark.django_db
def test_backfill_fills_blank_icons_only() -> None:
    cat = FeatureCategory.objects.create(name="Outdoor", slug="outdoor", icon="")
    blank = Feature.objects.create(name="Private pool", slug="pool", category=cat, icon="")
    kept = Feature.objects.create(name="BBQ", slug="bbq", category=cat, icon="custom-icon")

    _0012.forwards(global_apps, None)

    blank.refresh_from_db()
    kept.refresh_from_db()
    cat.refresh_from_db()
    assert blank.icon == "waves", "blank icon should be backfilled from the slug map"
    assert kept.icon == "custom-icon", "a pre-set icon must not be clobbered"
    assert cat.icon == "trees", "categories are backfilled too"
