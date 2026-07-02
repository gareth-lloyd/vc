"""Serializer for `Discount` and the promo-code lookup endpoint."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from pricing.models import Discount


class DiscountSerializer(serializers.ModelSerializer[Discount]):
    class Meta:
        model = Discount
        fields = [
            "id",
            "property",
            "name",
            "code",
            "rule_kind",
            "kind",
            "amount",
            "min_nights",
            "threshold_days",
            "valid_from",
            "valid_to",
            "max_uses",
            "uses_count",
            "is_active",
        ]
        # `property` comes from the URL in the nested create view; immutable on PATCH.
        read_only_fields = ["id", "property", "uses_count"]
        # The workbench sends `min_nights: null` for "no minimum"; the column is
        # NOT NULL default 0, so null is accepted and coerced below.
        extra_kwargs = {"min_nights": {"allow_null": True}}

    def validate_min_nights(self, value: int | None) -> int:
        return 0 if value is None else value

    def validate_code(self, value: str | None) -> str | None:
        # "" would occupy the UNIQUE index (unlike NULL, which may repeat) —
        # normalise blank to null, matching the form dialogs.
        return value or None

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        valid_from = attrs.get("valid_from", getattr(self.instance, "valid_from", None))
        valid_to = attrs.get("valid_to", getattr(self.instance, "valid_to", None))
        if valid_from is not None and valid_to is not None and valid_from > valid_to:
            raise serializers.ValidationError(
                {"valid_to": "valid_to must be on or after valid_from."},
            )
        return attrs


class DiscountLookupCodeSerializer(serializers.Serializer[None]):
    """Body for `POST /discounts:lookup-code`."""

    property_id = serializers.IntegerField(min_value=1)
    code = serializers.CharField(max_length=64)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    party = serializers.IntegerField(required=False, min_value=1)
