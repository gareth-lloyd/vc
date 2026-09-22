"""Serializers for `Feature` and `FeatureCategory`."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from properties.models import Feature, FeatureCategory
from properties.other_information_catalog import OTHER_INFORMATION_CATEGORY_SLUG


class FeatureCategorySerializer(serializers.ModelSerializer[FeatureCategory]):
    class Meta:
        model = FeatureCategory
        fields = ["id", "name", "slug", "description", "icon", "sort_order", "is_active"]
        read_only_fields = ["id"]

    def validate_slug(self, value: str) -> str:
        # The Features tab, the Zoho payload and the seeding stage all key on
        # this slug; a rename through the Tags admin silently empties all three.
        instance = self.instance
        if (
            instance is not None
            and instance.slug == OTHER_INFORMATION_CATEGORY_SLUG
            and value != OTHER_INFORMATION_CATEGORY_SLUG
        ):
            raise serializers.ValidationError(
                _(
                    "This slug is reserved: the Features tab, the Zoho export and "
                    "seeding key on it. Rename the category instead."
                )
            )
        return value


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
