"""Serializer for `PropertyCapacity` (one row per property)."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import PropertyCapacity

_CAPACITY_FIELDS = (
    "guests",
    "additional_guests",
    "bedrooms",
    "ensuites",
    "bathrooms",
    "size_sqm",
)


class PropertyCapacitySerializer(serializers.ModelSerializer[PropertyCapacity]):
    class Meta:
        model = PropertyCapacity
        fields = ("property", *_CAPACITY_FIELDS)
        read_only_fields = ["property"]
