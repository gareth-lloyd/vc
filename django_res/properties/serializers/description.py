"""Serializer for `PropertyDescription`."""

from __future__ import annotations

from rest_framework import serializers

from properties.models import PropertyDescription


class PropertyDescriptionSerializer(serializers.ModelSerializer[PropertyDescription]):
    class Meta:
        model = PropertyDescription
        fields = ["id", "property", "section", "body", "updated_at"]
        read_only_fields = ["id", "property", "section", "updated_at"]


class PropertyDescriptionWriteSerializer(serializers.Serializer[None]):
    """Validates the PUT payload for one section.

    Deliberately not a `ModelSerializer`: `body` is `TextField(blank=True)`, so
    DRF would derive `required=False` and a body-less PUT would silently blank
    hard-won copy; and `property`/`section` come from the URL, not the payload,
    so the upsert isn't expressible as a model save anyway. An explicit empty
    string stays valid — that's "clear this section".
    """

    body = serializers.CharField(allow_blank=True, trim_whitespace=False)
