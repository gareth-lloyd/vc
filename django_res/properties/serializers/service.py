"""Serializer for `PropertyService` (GAP-037)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from properties.models.services import PropertyService


class PropertyServiceSerializer(serializers.ModelSerializer[PropertyService]):
    class Meta:
        model = PropertyService
        fields = [
            "id",
            "property",
            "name",
            "copy",
            "notes",
            "applies_from",
            "applies_to",
            "sort_order",
            "is_active",
        ]
        read_only_fields = ["id", "property"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Mirror the model's check constraint as a 400 (not a 500 IntegrityError):
        # an absolute band must not run backwards; either end may be open (null).
        applies_from = attrs.get("applies_from", getattr(self.instance, "applies_from", None))
        applies_to = attrs.get("applies_to", getattr(self.instance, "applies_to", None))
        if applies_from and applies_to and applies_from > applies_to:
            raise serializers.ValidationError(
                {"applies_to": "applies_to must not be earlier than applies_from."}
            )
        return attrs
