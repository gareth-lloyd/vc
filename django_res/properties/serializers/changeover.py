"""Serializer for `ChangeOverRule`."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import ChangeOverRule


class ChangeOverRuleSerializer(serializers.ModelSerializer[ChangeOverRule]):
    # Map spec field names to model field names.
    weekday = serializers.CharField(source="day", max_length=8)
    effective_from = serializers.DateField(source="starts_on")
    effective_to = serializers.DateField(source="ends_on")

    class Meta:
        model = ChangeOverRule
        fields = ["id", "property", "weekday", "effective_from", "effective_to", "notes"]
        read_only_fields = ["id", "property"]
