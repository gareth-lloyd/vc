"""Feature catalogue + per-property m2m attachments.

Once per run: idempotent get_or_create of a small FeatureCategory + Feature
catalogue, then attach `features_per_property` random features to each
property. Knob: `features_per_property` (inclusive range). (0, 0) disables.
"""

from __future__ import annotations

from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from properties.enums import FeatureServiceType
from properties.models.features import Feature, FeatureCategory

_CATEGORIES = [
    ("Outdoor", "outdoor"),
    ("Kitchen", "kitchen"),
    ("Bedroom", "bedroom"),
    ("Bathroom", "bathroom"),
    ("Entertainment", "entertainment"),
]

_FEATURES = [
    # (slug, name, category_slug, service_type)
    ("pool", "Private pool", "outdoor", FeatureServiceType.AMENITY),
    ("hot-tub", "Hot tub", "outdoor", FeatureServiceType.AMENITY),
    ("bbq", "BBQ", "outdoor", FeatureServiceType.AMENITY),
    ("garden", "Garden", "outdoor", FeatureServiceType.AMENITY),
    ("sea-view", "Sea view", "outdoor", FeatureServiceType.AMENITY),
    ("dishwasher", "Dishwasher", "kitchen", FeatureServiceType.AMENITY),
    ("oven", "Oven", "kitchen", FeatureServiceType.AMENITY),
    ("coffee-machine", "Coffee machine", "kitchen", FeatureServiceType.AMENITY),
    ("welcome-pack", "Welcome pack", "kitchen", FeatureServiceType.INCLUDED_SERVICE),
    ("private-chef", "Private chef", "kitchen", FeatureServiceType.PAID_ADDON),
    ("king-bed", "King-size bed", "bedroom", FeatureServiceType.AMENITY),
    ("cot", "Cot available", "bedroom", FeatureServiceType.AMENITY),
    ("blackout", "Blackout blinds", "bedroom", FeatureServiceType.AMENITY),
    ("ensuite-bathroom", "Ensuite bathroom", "bathroom", FeatureServiceType.AMENITY),
    ("rain-shower", "Rain shower", "bathroom", FeatureServiceType.AMENITY),
    ("bath-tub", "Bath tub", "bathroom", FeatureServiceType.AMENITY),
    ("smart-tv", "Smart TV", "entertainment", FeatureServiceType.AMENITY),
    ("wifi", "Wi-Fi", "entertainment", FeatureServiceType.INCLUDED_SERVICE),
    ("games-room", "Games room", "entertainment", FeatureServiceType.AMENITY),
    ("daily-housekeeping", "Daily housekeeping", "entertainment", FeatureServiceType.PAID_ADDON),
]


def _ensure_catalogue() -> list[Feature]:
    categories: dict[str, FeatureCategory] = {}
    for name, slug in _CATEGORIES:
        cat, _ = FeatureCategory.objects.get_or_create(
            slug=slug,
            defaults={"name": name},
        )
        categories[slug] = cat
    features: list[Feature] = []
    for slug, name, cat_slug, service_type in _FEATURES:
        feature, _ = Feature.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "category": categories[cat_slug],
                "service_type": service_type,
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
