"""Serializers for `PropertyImage` and its action endpoints."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import PropertyImage


class PropertyImageSerializer(serializers.ModelSerializer[PropertyImage]):
    class Meta:
        model = PropertyImage
        fields = [
            "id",
            "property",
            "image",
            "kind",
            "name",
            "description",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "property", "created_at", "updated_at"]


class PropertyImageWriteSerializer(serializers.Serializer[PropertyImage]):
    """Attach an uploaded image to a property via its S3 key.

    The legacy `ImageField` write surface (multipart upload) is not used; the FE
    uploads to the signed URL, then POSTs the resulting key back here.
    """

    key = serializers.CharField(max_length=512)
    kind = serializers.CharField(max_length=16)
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)


class PropertyImageReorderSerializer(serializers.Serializer[None]):
    """Body: `{image_ids: [int, int, ...]}` — assigns `sort_order` by position."""

    image_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class PropertyImageSetHeroSerializer(serializers.Serializer[None]):
    image_id = serializers.IntegerField(min_value=1)
