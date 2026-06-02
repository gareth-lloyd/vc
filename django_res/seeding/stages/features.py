"""Feature catalogue + per-property m2m attachments.

Once per run: idempotent get_or_create of a small FeatureCategory + Feature
catalogue, then attach `features_per_property` random features to each
property. Knob: `features_per_property` (inclusive range). (0, 0) disables.
"""

from __future__ import annotations

from properties.enums import FeatureServiceType
from properties.models.features import Feature, FeatureCategory
from seeding.context import SeedContext
from seeding.registry import Stage, register

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


def _run(ctx: SeedContext) -> int:
    low, high = ctx.knobs.features_per_property
    if high <= 0:
        return 0
    if not ctx.properties:
        return 0
    catalogue = _ensure_catalogue()
    made = 0
    for prop in ctx.properties:
        n = min(ctx.rng.randint(low, high), len(catalogue))
        picks = ctx.rng.sample(catalogue, k=n)
        # Use `add` (idempotent on m2m) so reruns are safe.
        prop.features.add(*picks)
        made += n
    return made


register(Stage(name="features", run=_run, depends_on=("properties",)))
