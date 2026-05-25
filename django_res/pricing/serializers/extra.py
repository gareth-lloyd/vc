"""Serializer for `Extra`."""

from __future__ import annotations

from rest_framework import serializers

from pricing.models import Extra


class ExtraSerializer(serializers.ModelSerializer[Extra]):
    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = Extra
        fields = [
            "id",
            "property",
            "name",
            "description",
            "kind",
            "calc",
            "amount",
            "currency",
            "currency_code",
            "is_mandatory",
            "applies_from",
            "applies_to",
            "min_party",
            "max_party",
            "sort_order",
            "is_active",
            "notes",
        ]
        read_only_fields = ["id"]
