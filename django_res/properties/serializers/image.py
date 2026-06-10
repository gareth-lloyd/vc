"""Serializers for `PropertyImage` and its action endpoints."""

from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from properties.models import PropertyImage


class PropertyImageSerializer(serializers.ModelSerializer[PropertyImage]):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PropertyImage
        fields = [
            "id",
            "property",
            "image_url",
            "kind",
            "name",
            "description",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "property", "created_at", "updated_at"]

    def get_image_url(self, obj: PropertyImage) -> str | None:
        # Storage-generated: `/media/…` on local FileSystemStorage, an absolute
        # S3 URL on staging/prod. Same convention as `Property.hero_image_url`.
        if not obj.image:
            return None
        return obj.image.url


class PropertyImageWriteSerializer(serializers.Serializer[PropertyImage]):
    """Multipart upload: the image file plus its metadata, in one POST.

    Bytes land wherever `STORAGES["default"]` points — local MEDIA_ROOT in
    dev/test, the S3 bucket on staging/prod.
    """

    image = serializers.ImageField()
    kind = serializers.CharField(max_length=16)
    name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    sort_order = serializers.IntegerField(required=False, min_value=0)
    is_active = serializers.BooleanField(required=False)

    def validate_image(self, value: object) -> object:
        max_bytes: int = settings.MAX_IMAGE_BYTES
        size = getattr(value, "size", 0)
        if size > max_bytes:
            raise serializers.ValidationError(f"Image is {size} bytes; the maximum is {max_bytes}.")
        return value


class PropertyImageReorderSerializer(serializers.Serializer[None]):
    """Body: `{image_ids: [int, int, ...]}` — assigns `sort_order` by position."""

    image_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class PropertyImageSetHeroSerializer(serializers.Serializer[None]):
    image_id = serializers.IntegerField(min_value=1)
