"""Extra non-HERO PropertyImage rows per property.

`PropertyFactory` already creates one HERO row per property. This stage adds
`images_per_property` rows spread across the gallery / interior / exterior
kinds so dev/staging galleries are realistic.
"""

from __future__ import annotations

from properties.enums import ImageKind
from properties.factories import _villa_image_or_placeholder
from properties.models.images import PropertyImage
from seeding.context import SeedContext
from seeding.registry import Stage, register

# Non-HERO kinds — HERO is partial-unique per property, so we never add more.
# FLOOR_PLAN is deliberately absent: there is no stock floor-plan photo, so
# seeding one would only ever land the 1x1 placeholder.
_NON_HERO_KINDS = [
    ImageKind.INTERIOR,
    ImageKind.EXTERIOR,
    ImageKind.GALLERY,
]


def _run(ctx: SeedContext) -> int:
    low, high = ctx.knobs.images_per_property
    if high <= 0:
        return 0
    if not ctx.properties:
        return 0
    made = 0
    for prop in ctx.properties:
        slug = ctx.property_villa.get(prop.pk)
        n = ctx.rng.randint(low, high)
        for i in range(n):
            kind = _NON_HERO_KINDS[i % len(_NON_HERO_KINDS)]
            # Draw from the villa the `properties` stage assigned this property
            # (coherent with its HERO); any non-manifest prop falls back to the
            # 1x1 placeholder.
            PropertyImage.objects.create(
                property=prop,
                image=_villa_image_or_placeholder(slug, kind.value),
                kind=kind,
                name=f"{kind.label} {i + 1}",
                sort_order=i,
            )
            made += 1
    return made


register(Stage(name="gallery", run=_run, depends_on=("properties",)))
