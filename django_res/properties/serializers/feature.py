"""Serializers for `Feature` and `FeatureCategory`."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import Feature, FeatureCategory


class FeatureCategorySerializer(serializers.ModelSerializer[FeatureCategory]):
    class Meta:
        model = FeatureCategory
        fields = ["id", "name", "slug", "description", "icon", "sort_order", "is_active"]
        read_only_fields = ["id"]


class FeatureSerializer(serializers.ModelSerializer[Feature]):
    class Meta:
        model = Feature
        fields = [
            "id",
            "category",
            "name",
            "slug",
            "description",
            "icon",
            "sort_order",
            "is_active",
            "service_type",
        ]
        read_only_fields = ["id"]
