"""Serializer for `Extra`."""

from __future__ import annotations

from typing import Any

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
            "commissionable",
            "applies_from",
            "applies_to",
            "min_party",
            "max_party",
            "sort_order",
            "is_active",
            "notes",
        ]
        # `property` comes from the URL in the nested create view; immutable on PATCH.
        read_only_fields = ["id", "property"]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Mirror the model's CheckConstraints so bad ranges 400 instead of
        # surfacing as an IntegrityError 500.
        def effective(name: str) -> Any:
            return attrs[name] if name in attrs else getattr(self.instance, name, None)

        applies_from, applies_to = effective("applies_from"), effective("applies_to")
        if applies_from is not None and applies_to is not None and applies_from > applies_to:
            raise serializers.ValidationError(
                {"applies_to": "applies_to must be on or after applies_from."},
            )

        min_party, max_party = effective("min_party"), effective("max_party")
        if min_party is not None and max_party is not None and min_party > max_party:
            raise serializers.ValidationError(
                {"max_party": "max_party must be greater than or equal to min_party."},
            )
        return attrs


class ExtraDuplicateSerializer(serializers.Serializer[None]):
    """Input for `POST /extras/{id}:duplicate` (SMELL-009).

    `target_property_id` re-parents the clone (the view resolves it,
    404-ing unknown ids); `idempotency_key` dedupes retries per destination
    property. Absent, blank, and explicit-null all mean "not requested".
    """

    idempotency_key = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, default="", max_length=64
    )
    target_property_id = serializers.IntegerField(required=False, allow_null=True)
