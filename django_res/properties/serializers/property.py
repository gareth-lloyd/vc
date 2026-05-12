"""Property serializers — list, detail, and write shapes."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import Property


class PropertyListSerializer(serializers.ModelSerializer[Property]):
    """Lighter representation for list endpoints — no nested collections."""

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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PropertyDetailSerializer(serializers.ModelSerializer[Property]):
    """Full representation including small-cardinality nested collections."""

    feature_ids: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(
        source="features",
        many=True,
        read_only=True,
    )

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
            "legacy_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]


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
