"""Feature/category icons are seeded by the dev-seed stage (`_ensure_catalogue`).

(The idempotent `properties.0012` slug->icon backfill migration was folded into
the flattened `0001_initial`; its one-shot backfill test went with it.)
"""

from __future__ import annotations

import pytest

from properties.models.features import Feature, FeatureCategory
from seeding.stages.features import _ensure_catalogue


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
