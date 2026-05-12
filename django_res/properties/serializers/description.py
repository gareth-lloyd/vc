"""Serializer for `PropertyDescription`."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import PropertyDescription


class PropertyDescriptionSerializer(serializers.ModelSerializer[PropertyDescription]):
    class Meta:
        model = PropertyDescription
        fields = ["id", "property", "section", "body", "updated_at"]
        read_only_fields = ["id", "property", "section", "updated_at"]
