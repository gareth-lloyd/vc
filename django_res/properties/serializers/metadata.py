"""Serializers for `PropertyCategory` and `PropertyGroup`."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import PropertyCategory, PropertyGroup


class PropertyCategorySerializer(serializers.ModelSerializer[PropertyCategory]):
    class Meta:
        model = PropertyCategory
        fields = ["id", "name", "slug", "sort_order", "is_active"]
        read_only_fields = ["id"]


class PropertyGroupSerializer(serializers.ModelSerializer[PropertyGroup]):
    class Meta:
        model = PropertyGroup
        fields = ["id", "name", "description", "is_active", "legacy_id"]
        read_only_fields = ["id"]
