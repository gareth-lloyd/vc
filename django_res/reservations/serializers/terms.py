"""Serializer for `TermsVersion`."""

from __future__ import annotations

from rest_framework import serializers

from reservations.models.terms import TermsVersion


class TermsVersionSerializer(serializers.ModelSerializer[TermsVersion]):
    class Meta:
        model = TermsVersion
        fields = ["id", "version", "body_markdown", "is_current", "published_at", "created_at"]
        read_only_fields = ["id", "is_current", "published_at", "created_at"]
