"""Property serializers — list, detail, and write shapes."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import Property, PropertyCapacity

_CAPACITY_READ_FIELDS = (
    "guests",
    "additional_guests",
    "bedrooms",
    "ensuites",
    "bathrooms",
    "size_sqm",
)


class PropertyListSerializer(serializers.ModelSerializer[Property]):
    """Lighter representation for list endpoints — no nested collections.

    Carries a read-only, nullable `capacity` block (null when the property has
    no `PropertyCapacity` row) so callers — notably the quote builder — can tell
    a capacity-less property apart from one that simply has zero guests. This is
    a pure read addition; it does NOT change which rows the list returns.
    """

    capacity = serializers.SerializerMethodField()

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
            "group",
            "region",
            "capacity",
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


class PropertyDetailSerializer(serializers.ModelSerializer[Property]):
    """Full representation including small-cardinality nested collections."""

    feature_ids: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(
        source="features",
        many=True,
        read_only=True,
    )
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
            "group",
            "region",
            "feature_ids",
            "hero_image_url",
            "legacy_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def get_hero_image_url(self, obj: Property) -> str | None:
        return obj.hero_image_url()


class PropertyWriteSerializer(serializers.ModelSerializer[Property]):
    """Write shape for create / partial update.

    `status` is not directly writable here — lifecycle changes go through the
    `:activate` / `:archive` / `:restore` action endpoints.
    """

    class Meta:
        model = Property
        fields = [
            "name",
            "display_name",
            "slug",
            "licence_number",
            "channel",
            "category",
            "group",
            "region",
            "features",
            "legacy_id",
        ]
