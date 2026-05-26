"""Extra non-HERO PropertyImage rows per property.

`PropertyFactory` already creates one HERO row per property. This stage adds
`images_per_property` rows spread across the gallery / interior / exterior /
floor-plan kinds so dev/staging galleries are realistic.
"""

from __future__ import annotations

from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from properties.enums import ImageKind
from properties.factories import _tiny_png
from properties.models.images import PropertyImage

# Non-HERO kinds — HERO is partial-unique per property, so we never add more.
_NON_HERO_KINDS = [
    ImageKind.INTERIOR,
    ImageKind.EXTERIOR,
    ImageKind.GALLERY,
    ImageKind.FLOOR_PLAN,
]


def _run(ctx: SeedContext) -> int:
    low, high = ctx.knobs.images_per_property
    if high <= 0:
        return 0
    if not ctx.properties:
        return 0
    made = 0
    for prop in ctx.properties:
        n = ctx.rng.randint(low, high)
        for i in range(n):
            kind = _NON_HERO_KINDS[i % len(_NON_HERO_KINDS)]
            PropertyImage.objects.create(
                property=prop,
                image=_tiny_png(),
                kind=kind,
                name=f"{kind.label} {i + 1}",
                sort_order=i,
            )
            made += 1
    return made


register(Stage(name="gallery", run=_run, depends_on=("properties",)))
