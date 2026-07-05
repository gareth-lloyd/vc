"""Property serializers — list, detail, and write shapes."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rest_framework import serializers

from properties.models import Feature, Property, PropertyCapacity, PropertyFeature

_CAPACITY_READ_FIELDS = (
    "guests",
    "additional_guests",
    "bedrooms",
    "ensuites",
    "bathrooms",
    "size_sqm",
)


class _CalendarSourceMixin(serializers.Serializer[Property]):
    """Read-only calendar-source fields shared by the list and detail shapes (GAP-034).

    `has_active_ical_feed` tells sales the on-screen availability is the latest
    auto-synced source; `calendar_url` is the owner's online (non-iCal) calendar
    webpage. Precedence (badge wins over link) is a front-end concern — the API
    exposes both. The secret feed `url` is never serialized.
    """

    has_active_ical_feed = serializers.SerializerMethodField()
    calendar_url = serializers.SerializerMethodField()
    # GAP-033 availability-freshness signals. The two plain timestamps
    # (availability_owner_updated_at / availability_confirmed_at) are mapped
    # straight from the model via each Meta.fields list. The two below need
    # derivation:
    #   - confirmed_by_name resolves the staff actor FK to a display name.
    #   - calendar_last_imported_at (Signal 2) reads the viewset's scalar
    #     `Subquery` annotation, falling back to None off the annotated path.
    availability_confirmed_by_name = serializers.SerializerMethodField()
    calendar_last_imported_at = serializers.SerializerMethodField()

    def get_availability_confirmed_by_name(self, obj: Property) -> str | None:
        # `select_related("availability_confirmed_by")` on the viewset keeps this
        # free; the FK is nullable, so an unconfirmed property returns None.
        user = obj.availability_confirmed_by
        if user is None:
            return None
        return user.get_full_name() or user.email

    def get_calendar_last_imported_at(self, obj: Property) -> Any:
        # Latest active-feed `last_polled_at`, annotated as a scalar `Subquery`
        # on the list/detail queryset (no per-row query). Fresh, non-annotated
        # instances (create/duplicate) lack the attribute → None.
        return getattr(obj, "calendar_last_imported_at", None)

    def get_has_active_ical_feed(self, obj: Property) -> bool:
        # The list viewset annotates this via a scalar `Exists` (no per-row
        # query). Fresh, non-annotated instances from `create`/`duplicate` lack
        # the attribute, so fall back to a single existence check on the object.
        annotated = getattr(obj, "has_active_ical_feed", None)
        if annotated is not None:
            return bool(annotated)
        return obj.calendar_feeds.filter(is_active=True).exists()

    def get_calendar_url(self, obj: Property) -> str | None:
        # `select_related("settings")` on the viewset makes this free; settings-
        # less instances (fresh `create`/`duplicate`) hit the guard and return
        # None after one cheap SELECT — not an N+1 (single object).
        try:
            return obj.settings.calendar_url
        except ObjectDoesNotExist:
            return None


class PropertyListSerializer(_CalendarSourceMixin, serializers.ModelSerializer[Property]):
    """Lighter representation for list endpoints — no nested collections.

    Carries a read-only, nullable `capacity` block (null when the property has
    no `PropertyCapacity` row) so callers — notably the quote builder — can tell
    a capacity-less property apart from one that simply has zero guests. This is
    a pure read addition; it does NOT change which rows the list returns.
    """

    capacity = serializers.SerializerMethodField()
    available_for_range = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            "id",
            "name",
            "display_name",
            "slug",
            "licence_number",
            "status",
            "channel",
            "category",
            "region",
            "capacity",
            "available_for_range",
            "has_active_ical_feed",
            "calendar_url",
            "availability_owner_updated_at",
            "availability_confirmed_at",
            "availability_confirmed_by_name",
            "calendar_last_imported_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_capacity(self, obj: Property) -> dict[str, object] | None:
        capacity: PropertyCapacity | None = getattr(obj, "capacity", None)
        if capacity is None:
            return None
        data: dict[str, object] = {
            field: getattr(capacity, field) for field in _CAPACITY_READ_FIELDS
        }
        # Serialise the decimal as a string, matching the dedicated capacity
        # endpoint (DRF `DecimalField`); a raw Decimal would render as a JSON
        # number here and drift from that contract.
        data["size_sqm"] = None if capacity.size_sqm is None else str(capacity.size_sqm)
        return data

    def get_available_for_range(self, obj: Property) -> bool | None:
        """Whether the row is free across the request's `date_from..date_to`.

        Computed against the bulk unavailable-id set the view places in the
        serializer context when the list request carries a date range; `None`
        (no date range) means "availability undefined", never a misleading
        `True`. Lets `include_unavailable=true` callers — the quote builder —
        badge blocked villas instead of silently offering them.
        """
        unavailable_ids = self.context.get("unavailable_property_ids")
        if unavailable_ids is None:
            return None
        return obj.pk not in unavailable_ids


class PropertyDetailSerializer(_CalendarSourceMixin, serializers.ModelSerializer[Property]):
    """Full representation including small-cardinality nested collections."""

    feature_ids = serializers.SerializerMethodField()
    hero_image_url = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            "id",
            "name",
            "display_name",
            "slug",
            "licence_number",
            "status",
            "channel",
            "category",
            "region",
            "feature_ids",
            "hero_image_url",
            "has_active_ical_feed",
            "calendar_url",
            "availability_owner_updated_at",
            "availability_confirmed_at",
            "availability_confirmed_by_name",
            "calendar_last_imported_at",
            "legacy_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def get_feature_ids(self, obj: Property) -> list[int]:
        # Per-villa order (GAP-022): walk the `PropertyFeature` through-links,
        # which `Meta.ordering` sorts by `sort_order`. NOT `obj.features.all()`,
        # which would sort by Feature's global rank. This reads only the
        # `feature_id` column already on each through-row, so it's a single
        # ordered query regardless of feature count — no N+1, no prefetch needed.
        return [link.feature_id for link in obj.feature_links.all()]

    def get_hero_image_url(self, obj: Property) -> str | None:
        return obj.hero_image_url()


class PropertyWriteSerializer(serializers.ModelSerializer[Property]):
    """Write shape for create / partial update.

    `status` is not directly writable here — lifecycle changes go through the
    `:activate` / `:archive` / `:restore` action endpoints.
    """

    # Declared explicitly: DRF auto-marks a `through`-model M2M as read-only, so
    # without this `features` would never reach `validated_data` and the ordered
    # diff-writer below would be a no-op. The LIST ORDER is meaningful — it
    # becomes each link's `sort_order` (GAP-022).
    features = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Feature.objects.all(),
        required=False,
    )

    class Meta:
        model = Property
        fields = [
            "name",
            "display_name",
            "slug",
            "licence_number",
            "channel",
            "category",
            "region",
            "features",
            "legacy_id",
        ]

    def create(self, validated_data: dict[str, Any]) -> Property:
        # Handle `features` ourselves so list ORDER becomes `sort_order`; DRF's
        # default `.set()` would discard order and assign every row sort_order=0.
        features = validated_data.pop("features", None)
        instance = super().create(validated_data)
        if features is not None:
            self._sync_feature_order(instance, features)
        return instance

    def update(self, instance: Property, validated_data: dict[str, Any]) -> Property:
        # `features` absent on a partial PATCH → leave the existing links alone.
        has_features = "features" in validated_data
        features = validated_data.pop("features", None)
        instance = super().update(instance, validated_data)
        if has_features:
            self._sync_feature_order(instance, features or [])
        return instance

    @staticmethod
    def _sync_feature_order(instance: Property, features: list[Any]) -> None:
        """Diff the property's feature links against the desired ORDERED list,
        writing `sort_order` = list position. Per-row `create`/`delete`/`save`
        (never `bulk_*`) so each change fires its audit signal (FG-017); the
        `sort_order != position` guard means a pure reorder touches only the
        rows that actually moved, keeping the audit trail quiet. Duplicate ids
        collapse to their first position (the unique constraint forbids repeats).
        """
        ordered_ids = list(dict.fromkeys(feature.pk for feature in features))
        with transaction.atomic():
            existing = {link.feature_id: link for link in instance.feature_links.all()}
            for feature_id, link in existing.items():
                if feature_id not in ordered_ids:
                    link.delete()
            for position, feature_id in enumerate(ordered_ids):
                existing_link = existing.get(feature_id)
                if existing_link is None:
                    PropertyFeature.objects.create(
                        property=instance, feature_id=feature_id, sort_order=position
                    )
                elif existing_link.sort_order != position:
                    existing_link.sort_order = position
                    existing_link.save(update_fields=["sort_order"])
