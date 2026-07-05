"""Serializer for `PropertyCategory`."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import PropertyCategory


class PropertyCategorySerializer(serializers.ModelSerializer[PropertyCategory]):
    class Meta:
        model = PropertyCategory
        fields = ["id", "name", "slug", "sort_order", "is_active"]
        read_only_fields = ["id"]
