"""Property lifecycle transitions and duplication.

`Property.status` is a tiny state machine: draft → active, draft|active → archived,
archived → draft (restore). All business logic for these transitions plus
duplicate / collection-replace lives here so views stay thin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import transaction

from core.transitions import transition
from properties.enums import PROPERTY_ALLOWED_TRANSITIONS, DescriptionSection, PropertyStatus
from properties.models import (
    Collection,
    CollectionMembership,
    Property,
    PropertyDescription,
    PropertyFeature,
    PropertyImage,
)
from properties.services.defaults import snapshot_defaults
from properties.services.location import ensure_property_location

if TYPE_CHECKING:
    from collections.abc import Iterable


class PropertyLifecycleService:
    """Pure-Python orchestration for Property state changes."""

    @classmethod
    def activate(cls, property: Property) -> Property:
        transition(property, PropertyStatus.ACTIVE.value, table=PROPERTY_ALLOWED_TRANSITIONS)
        return property

    @classmethod
    def archive(cls, property: Property) -> Property:
        transition(property, PropertyStatus.ARCHIVED.value, table=PROPERTY_ALLOWED_TRANSITIONS)
        return property

    @classmethod
    def restore(cls, property: Property) -> Property:
        transition(property, PropertyStatus.DRAFT.value, table=PROPERTY_ALLOWED_TRANSITIONS)
        return property

    @classmethod
    @transaction.atomic
    def duplicate(cls, property: Property, *, new_slug: str | None = None) -> Property:
        """Clone the villa + its descriptions and image rows.

        Rate plans, bookings, and holds are intentionally not cloned — the
        operator wires those up post-duplicate. Settings/finance are NOT copied
        from the original either: the clone gets a fresh snapshot of the global
        `PropertyDefaults`, exactly like an API-created property (GAP-070).
        """
        original_pk = property.pk
        # Clone MANUAL features only (GAP-067): a derived feature must not become
        # a permanent manual link on the clone. The clone has no rooms yet, so
        # `recompute_derived_features` rebuilds its derived set once rooms exist.
        features = list(
            PropertyFeature.objects.filter(property=property, is_derived=False).values_list(
                "feature_id", flat=True
            )
        )
        clone = Property.objects.get(pk=original_pk)
        clone.pk = None
        clone.slug = new_slug or f"{property.slug}-copy"
        clone.display_name = f"{property.display_name} (copy)"
        clone.status = PropertyStatus.DRAFT.value
        clone.save()
        if features:
            clone.features.set(features)
        # Website copy carries over; staff-only notes do not — they are specific
        # to the original property and would read as fact on the clone. That
        # includes `other_information` (the Features-tab prose, GAP-091) and
        # `rooms` (GAP-092's blurb): both are public copy, and the tags they sit
        # beside are cloned via `features` above, so cloning the text keeps the
        # pair together.
        for desc in PropertyDescription.objects.filter(property_id=original_pk).exclude(
            section=DescriptionSection.INTERNAL_NOTES
        ):
            PropertyDescription.objects.create(
                property=clone,
                section=desc.section,
                body=desc.body,
            )
        for image in PropertyImage.objects.filter(property_id=original_pk):
            PropertyImage.objects.create(
                property=clone,
                image=image.image,
                kind=image.kind,
                name=image.name,
                description=image.description,
                sort_order=image.sort_order,
                is_active=image.is_active,
            )
        # Provision a default location so the clone matches API-created
        # properties (which provision on create) rather than relying on a later
        # lazy heal.
        ensure_property_location(clone)
        snapshot_defaults(clone)
        return clone

    # ------------------------------------------------------------------
    # Collection membership replace
    # ------------------------------------------------------------------
    @classmethod
    @transaction.atomic
    def replace_collection_memberships(
        cls,
        property: Property,
        memberships: Iterable[dict[str, Any]],
    ) -> list[CollectionMembership]:
        """Upsert the requested memberships and remove any not in the request."""
        keep_ids: list[int] = []
        result: list[CollectionMembership] = []
        for entry in memberships:
            collection = cls._resolve_collection(entry["collection"])
            membership, _ = CollectionMembership.objects.update_or_create(
                property=property,
                collection=collection,
                defaults={
                    "sort_order": entry.get("sort_order", 0),
                    "featured_until": entry.get("featured_until"),
                    "description": entry.get("description", ""),
                },
            )
            keep_ids.append(membership.pk)
            result.append(membership)
        CollectionMembership.objects.filter(property=property).exclude(pk__in=keep_ids).delete()
        return result

    @staticmethod
    def _resolve_collection(value: str | int) -> Collection:
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return Collection.objects.get(pk=int(value))
        return Collection.objects.get(slug=value)
