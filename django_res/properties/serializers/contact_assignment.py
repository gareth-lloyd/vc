"""Serializer for `PropertyContactAssignment`."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import PropertyContactAssignment


class PropertyContactAssignmentSerializer(serializers.ModelSerializer[PropertyContactAssignment]):
    class Meta:
        model = PropertyContactAssignment
        fields = [
            "id",
            "property",
            "contact",
            "role",
            "start_date",
            "end_date",
            "is_primary",
        ]
        read_only_fields = ["id", "property"]
