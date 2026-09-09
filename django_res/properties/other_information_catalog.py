"""Starter vocabulary for the "Other information" tags (GAP-091).

Legacy has no tag table: "Other Information" is feature category `Code=60`
(`VillaFeaturesCategory.Id=8`) of the single `VillaFeatures` catalogue, and
the tags are its features. We keep that shape — a `FeatureCategory` plus one
`Feature` per tag, assigned through `PropertyFeature` — so the WordPress site
can facet on `slug`.

This module is a **dev-seed convenience, not a migration**. Prod and staging
are loader-first: `FeatureCategoryLoader` / `FeatureLoader` create these very
rows from the legacy dump, upserting on `legacy_id`. The sync therefore
resolves rows by `legacy_id` FIRST (a loader-written row whose name — hence
slug — was later edited must still be adopted, not duplicated), then by
slug, and only creates what neither finds. Slugs are derived exactly as the
loaders derive them (`slugify(name)[:128]`), so whichever side runs first,
the other updates in place (`data_migration/tests/test_feature_loaders.py`
pins both orders). Migration-seeding was rejected: the test suite asserts
exact feature counts and creates same-slug features freely.

Excluded on purpose (verified against `ResSystem/Database/DbScript.sql`):
`152 Wheelchair accessible` (soft-deleted in legacy, never loads), `298 Sea
View` (mapped to eight legacy categories; the loader files it under
"Included Features" and the dev catalogue already owns `sea-view`), and
`304 Dev Feature` (live junk — deactivate in the Tags admin after cutover).
"""

from __future__ import annotations

from django.utils.text import slugify

from properties.enums import FeatureServiceType
from properties.models import Feature, FeatureCategory

_CATEGORY_NAME = "Other Information"  # exactly the legacy name — the loader slugifies it
OTHER_INFORMATION_CATEGORY_SLUG = slugify(_CATEGORY_NAME)  # "other-information"
_CATEGORY_LEGACY_ID = "8"  # VillaFeaturesCategory.Id
_CATEGORY_SORT_ORDER = 60  # VillaFeaturesCategory.Code, which the loader maps to sort_order
_CATEGORY_ICON = "info"

# (name, legacy VillaFeatures.Id, lucide-react icon). Row index = sort_order;
# slug = slugify(name), the loader's derivation.
STARTER_TAGS: tuple[tuple[str, str, str], ...] = (
    ("Wheelchair access", "96", "accessibility"),
    ("No pets", "124", "ban"),
    ("No smoking indoors", "125", "cigarette-off"),
    ("Children not allowed", "126", "baby"),
    ("Weddings and events", "127", "party-popper"),
    ("Pets allowed", "128", "paw-print"),
    ("Resident pets", "129", "cat"),
    ("Fenced pool", "130", "fence"),
    ("Service kitchen", "131", "chef-hat"),
    ("Staff accommodation", "132", "users"),
    ("No large parties", "271", "volume-x"),
)


def tag_slug(name: str) -> str:
    """The slug the legacy `FeatureLoader` would write for this name."""
    return slugify(name)[:128]


def _resolve_category() -> FeatureCategory:
    category = (
        FeatureCategory.objects.filter(legacy_id=_CATEGORY_LEGACY_ID).order_by("pk").first()
        or FeatureCategory.objects.filter(slug=OTHER_INFORMATION_CATEGORY_SLUG).first()
    )
    if category is not None:
        return category
    return FeatureCategory.objects.create(
        name=_CATEGORY_NAME,
        slug=OTHER_INFORMATION_CATEGORY_SLUG,
        legacy_id=_CATEGORY_LEGACY_ID,
        sort_order=_CATEGORY_SORT_ORDER,
        icon=_CATEGORY_ICON,
    )


def sync_other_information_tags() -> int:
    """Ensure the category and every starter tag exist; returns tags created.

    Idempotent and never clobbers an existing row: a tag already present by
    `legacy_id` (loader-written, possibly renamed) or by slug (a same-slug
    feature filed elsewhere) is left exactly as it is.
    """
    category = _resolve_category()
    created_count = 0
    for sort_order, (name, legacy_id, icon) in enumerate(STARTER_TAGS):
        if Feature.objects.filter(legacy_id=legacy_id).exists():
            continue
        slug = tag_slug(name)
        if Feature.objects.filter(slug=slug).exists():
            continue
        Feature.objects.create(
            name=name,
            slug=slug,
            category=category,
            legacy_id=legacy_id,
            sort_order=sort_order,
            icon=icon,
            service_type=FeatureServiceType.AMENITY,
            is_active=True,
        )
        created_count += 1
    return created_count
