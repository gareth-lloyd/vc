"""Feature catalogue + per-property m2m attachments.

Once per run: idempotent get_or_create of a small FeatureCategory + Feature
catalogue, then attach `features_per_property` random features to each
property. Knob: `features_per_property` (inclusive range). (0, 0) disables.

Also seeds the GAP-091 "Other information" tag vocabulary
(`properties.other_information_catalog`) — on every profile, ahead of the
knob gates, so even a `happy` DB has the Tags admin populated — and hangs two
tags on each villa. Tag picks draw from a **private** `random.Random`, never
`ctx.rng` (the `room_attributes` convention), so the main picks stay
byte-identical to the pre-GAP-091 stream.
"""

from __future__ import annotations

import random

from properties.enums import FeatureServiceType
from properties.models.features import Feature, FeatureCategory
from properties.other_information_catalog import (
    OTHER_INFORMATION_CATEGORY_SLUG,
    sync_other_information_tags,
)
from seeding.context import SeedContext
from seeding.registry import Stage, register

# Stable, private seed for the tag picks: decoupled from ctx.rng.
_TAG_SEED = 0x600D0091
_TAGS_PER_PROPERTY = 2

_CATEGORIES = [
    # (name, slug, icon) — icon is a lucide-react icon name (kebab-case).
    ("Outdoor", "outdoor", "trees"),
    ("Kitchen", "kitchen", "utensils-crossed"),
    ("Bedroom", "bedroom", "bed-double"),
    ("Bathroom", "bathroom", "bath"),
    ("Entertainment", "entertainment", "tv"),
]

_FEATURES = [
    # (slug, name, category_slug, service_type, icon)
    ("pool", "Private pool", "outdoor", FeatureServiceType.AMENITY, "waves"),
    ("hot-tub", "Hot tub", "outdoor", FeatureServiceType.AMENITY, "droplets"),
    ("bbq", "BBQ", "outdoor", FeatureServiceType.AMENITY, "flame"),
    ("garden", "Garden", "outdoor", FeatureServiceType.AMENITY, "sprout"),
    ("sea-view", "Sea view", "outdoor", FeatureServiceType.AMENITY, "sailboat"),
    ("dishwasher", "Dishwasher", "kitchen", FeatureServiceType.AMENITY, "utensils"),
    ("oven", "Oven", "kitchen", FeatureServiceType.AMENITY, "cooking-pot"),
    ("coffee-machine", "Coffee machine", "kitchen", FeatureServiceType.AMENITY, "coffee"),
    ("welcome-pack", "Welcome pack", "kitchen", FeatureServiceType.INCLUDED_SERVICE, "gift"),
    ("private-chef", "Private chef", "kitchen", FeatureServiceType.PAID_ADDON, "chef-hat"),
    ("king-bed", "King-size bed", "bedroom", FeatureServiceType.AMENITY, "bed-double"),
    ("cot", "Cot available", "bedroom", FeatureServiceType.AMENITY, "baby"),
    ("blackout", "Blackout blinds", "bedroom", FeatureServiceType.AMENITY, "blinds"),
    ("ensuite-bathroom", "Ensuite bathroom", "bathroom", FeatureServiceType.AMENITY, "shower-head"),
    ("rain-shower", "Rain shower", "bathroom", FeatureServiceType.AMENITY, "droplets"),
    ("bath-tub", "Bath tub", "bathroom", FeatureServiceType.AMENITY, "bath"),
    ("smart-tv", "Smart TV", "entertainment", FeatureServiceType.AMENITY, "tv"),
    ("wifi", "Wi-Fi", "entertainment", FeatureServiceType.INCLUDED_SERVICE, "wifi"),
    ("games-room", "Games room", "entertainment", FeatureServiceType.AMENITY, "gamepad-2"),
    (
        "daily-housekeeping",
        "Daily housekeeping",
        "entertainment",
        FeatureServiceType.PAID_ADDON,
        "sparkles",
    ),
]


def _ensure_catalogue() -> list[Feature]:
    categories: dict[str, FeatureCategory] = {}
    for name, slug, icon in _CATEGORIES:
        cat, _ = FeatureCategory.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "icon": icon},
        )
        categories[slug] = cat
    features: list[Feature] = []
    for slug, name, cat_slug, service_type, icon in _FEATURES:
        feature, _ = Feature.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "category": categories[cat_slug],
                "service_type": service_type,
                "icon": icon,
            },
        )
        features.append(feature)
    return features


def _other_information_tags() -> list[Feature]:
    """The active GAP-091 "Other information" vocabulary, in catalog order."""
    return list(
        Feature.objects.filter(
            category__slug=OTHER_INFORMATION_CATEGORY_SLUG, is_active=True
        ).order_by("sort_order", "pk")
    )


def _run(ctx: SeedContext) -> int:
    # Vocabulary first: it must exist on every profile (the `happy` knobs are
    # (0, 0)), only the per-villa assignment below is gated.
    sync_other_information_tags()
    low, high = ctx.knobs.features_per_property
    if high <= 0:
        return 0
    if not ctx.properties:
        return 0
    catalogue = _ensure_catalogue()
    tags = _other_information_tags()
    tag_rng = random.Random(_TAG_SEED)
    made = 0
    for prop in ctx.properties:
        n = min(ctx.rng.randint(low, high), len(catalogue))
        picks = ctx.rng.sample(catalogue, k=n)
        tag_picks = tag_rng.sample(tags, k=min(_TAGS_PER_PROPERTY, len(tags)))
        # Use `add` (idempotent on m2m) so reruns are safe.
        prop.features.add(*picks, *tag_picks)
        made += n + len(tag_picks)
    return made


register(Stage(name="features", run=_run, depends_on=("properties",)))
