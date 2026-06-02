"""Marketing Collections + CollectionMembership rows.

Creates `n_collections` Collections, then attaches an overlapping random
subset of properties to each via CollectionMembership.

Memberships are `(collection, property)` unique — `add()` is idempotent so
re-running won't collide, but we still cap attachments per property to keep
the spread looking realistic.
"""

from __future__ import annotations

from typing import Any, cast

from properties.factories import CollectionFactory
from properties.models.features import CollectionMembership
from seeding.context import SeedContext
from seeding.registry import Stage, register


def _run(ctx: SeedContext) -> int:
    if ctx.knobs.n_collections <= 0:
        return 0
    if not ctx.properties:
        return 0
    made = 0
    for _ in range(ctx.knobs.n_collections):
        collection = cast(Any, CollectionFactory())
        # Each collection picks 30-70% of the property pool - overlaps with
        # the next collection naturally because we re-sample.
        n_props = max(1, int(len(ctx.properties) * ctx.rng.uniform(0.3, 0.7)))
        picks = ctx.rng.sample(ctx.properties, k=min(n_props, len(ctx.properties)))
        for j, prop in enumerate(picks):
            _, created = CollectionMembership.objects.get_or_create(
                collection=collection,
                property=prop,
                defaults={"sort_order": j},
            )
            if created:
                made += 1
    return made


register(Stage(name="collections", run=_run, depends_on=("properties",)))
