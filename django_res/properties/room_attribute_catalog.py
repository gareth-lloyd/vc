"""Canonical starter rows for the `RoomAttribute` catalog (GAP-064).

`sync_room_attributes()` is the single source of seed truth: migration
`properties.0027` calls it at `migrate` time, and it is safe to re-invoke
later (idempotent `get_or_create` keyed on slug, so curator edits are never
clobbered).

Implication linking is **set-if-NULL and re-invocable**: `Feature` rows are
not migration-seeded, so at `migrate` time on a fresh DB every candidate
lookup misses and `implies_property_feature` stays NULL. Re-running the sync
after Features exist (e.g. via `backfill_room_attrs`, or after `loadlegacy` /
`seed_dev`) fills the link — but only when it is currently NULL, so a
curator's explicit choice always wins.
"""

from __future__ import annotations

from typing import Any

from properties.models import Feature, RoomAttribute

# (slug, name, icon, sort_order, candidate implies-feature slugs).
# Slugs are the stable machine key — the backfill keyword map and tests key on
# them; `name` is the curator-editable label. Icons are lucide-react names.
STARTER_ATTRIBUTES: tuple[tuple[str, str, str, int, tuple[str, ...]], ...] = (
    ("aircon", "Air conditioning", "air-vent", 10, ()),
    ("ceiling_fan", "Ceiling fan", "fan", 20, ()),
    ("sea_view", "Sea view", "waves", 30, ("sea-view", "sea-views")),
    ("balcony", "Balcony", "door-open", 40, ()),
    ("terrace", "Terrace", "sun", 50, ()),
    ("wheelchair", "Wheelchair accessible", "accessibility", 60, ("accessibility",)),
    ("in_room_safe", "In-room safe", "lock", 70, ()),
    ("hairdryer", "Hairdryer", "wind", 80, ()),
    ("mini_fridge", "Mini fridge", "refrigerator", 90, ()),
)


def starter_slugs() -> set[str]:
    return {slug for slug, *_ in STARTER_ATTRIBUTES}


def sync_room_attributes(
    *,
    model: Any = RoomAttribute,
    feature_model: Any = Feature,
) -> int:
    """Ensure every starter catalog row exists; returns rows created.

    `model`/`feature_model` let migration 0027 pass historical models
    (the comms `0003_seed_templates` pattern).
    """
    created_count = 0
    for slug, name, icon, sort_order, feature_candidates in STARTER_ATTRIBUTES:
        attr, created = model.objects.get_or_create(
            slug=slug,
            defaults={"name": name, "icon": icon, "sort_order": sort_order},
        )
        if created:
            created_count += 1
        if attr.implies_property_feature_id is None and feature_candidates:
            feature = feature_model.objects.filter(slug__in=feature_candidates).first()
            if feature is not None:
                attr.implies_property_feature = feature
                attr.save(update_fields=["implies_property_feature"])
    return created_count
