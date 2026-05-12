"""Serializer for the system-wide settings singleton."""

from __future__ import annotations

from rest_framework import serializers

from core.models import SystemSettings


class SystemSettingsSerializer(serializers.ModelSerializer[SystemSettings]):
    class Meta:
        model = SystemSettings
        fields = ["settings", "updated_at"]
        read_only_fields = ["updated_at"]
