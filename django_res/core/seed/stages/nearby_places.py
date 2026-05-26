"""Nearby place catalogue + per-property attachments.

Once per run: idempotent NearbyPlaceTypes (restaurant, beach, airport, …).
Per property: create `nearby_per_property` PropertyNearbyPlace rows with
random distances.
"""

from __future__ import annotations

from decimal import Decimal

from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from properties.models.geo import NearbyPlaceType, PropertyNearbyPlace

_PLACE_TYPES = ["Restaurant", "Beach", "Airport", "Supermarket", "Hospital"]


def _ensure_types() -> list[NearbyPlaceType]:
    types: list[NearbyPlaceType] = []
    for name in _PLACE_TYPES:
        place_type, _ = NearbyPlaceType.objects.get_or_create(name=name)
        types.append(place_type)
    return types


def _run(ctx: SeedContext) -> int:
    low, high = ctx.knobs.nearby_per_property
    if high <= 0:
        return 0
    if not ctx.properties:
        return 0
    types = _ensure_types()
    made = 0
    for prop in ctx.properties:
        n = ctx.rng.randint(low, high)
        for i in range(n):
            place_type = types[i % len(types)]
            # Distances 0.1km-25km, two decimal places.
            distance_km = Decimal(f"{ctx.rng.uniform(0.1, 25):.2f}")
            PropertyNearbyPlace.objects.create(
                property=prop,
                place_type=place_type,
                name=f"{place_type.name} {i + 1}",
                distance_km=distance_km,
                sort_order=i,
            )
            made += 1
    return made


register(Stage(name="nearby_places", run=_run, depends_on=("properties",)))
