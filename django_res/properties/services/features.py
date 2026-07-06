"""Derive property features from room attributes (GAP-067).

The room is the structured source of truth (GAP-064): a `RoomAttribute` may
carry `implies_property_feature`. `recompute_derived_features` reconciles the
`is_derived=True` `PropertyFeature` links on a property to match the union of
those implications across all its rooms — so a fact typed once on a room shows
up on the property without re-entry.

Precedence is manual-wins: the recompute manages ONLY derived links. A feature
already present as a MANUAL link (`is_derived=False`) is never duplicated and
never demoted; a manual add of a derived feature promotes it (handled in
`PropertyWriteSerializer._sync_feature_order`, not here).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from properties.models import PropertyFeature, RoomAttributeAssignment

if TYPE_CHECKING:
    from properties.models import Property


def recompute_derived_features(property_obj: Property) -> dict[str, int]:
    """Reconcile `property_obj`'s derived feature links to match its rooms.

    Adds a `is_derived=True` link for each implied feature not already present
    (manual or derived), deletes derived links no longer implied, and leaves
    manual links untouched. Per-row `.create()`/`.delete()` (never `bulk_*`) so
    each change fires its `PropertyFeature` audit signal (FG-017). Returns
    `{"added": n, "removed": m}`.
    """
    desired: set[int] = set(
        RoomAttributeAssignment.objects.filter(
            room__property=property_obj,
            attribute__implies_property_feature__isnull=False,
        ).values_list("attribute__implies_property_feature_id", flat=True)
    )
    added = removed = 0
    with transaction.atomic():
        links = list(property_obj.feature_links.all())
        manual_ids = {link.feature_id for link in links if not link.is_derived}
        derived_by_feature = {link.feature_id: link for link in links if link.is_derived}

        # Remove derived links no longer implied by any room.
        for feature_id, link in derived_by_feature.items():
            if feature_id not in desired:
                link.delete()
                removed += 1

        # Add derived links for implied features not already present. A feature
        # already MANUAL stays manual (skip); an existing derived link stays.
        next_sort = max((link.sort_order for link in links), default=-1) + 1
        for feature_id in desired:
            if feature_id in manual_ids or feature_id in derived_by_feature:
                continue
            PropertyFeature.objects.create(
                property=property_obj,
                feature_id=feature_id,
                sort_order=next_sort,
                is_derived=True,
            )
            next_sort += 1
            added += 1
    return {"added": added, "removed": removed}
