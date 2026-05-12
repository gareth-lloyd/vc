"""Serializer for `Discount` and the promo-code lookup endpoint."""

from __future__ import annotations

from rest_framework import serializers

from pricing.models import Discount


class DiscountSerializer(serializers.ModelSerializer[Discount]):
    class Meta:
        model = Discount
        fields = [
            "id",
            "card",
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
        read_only_fields = ["id", "uses_count"]


class DiscountLookupCodeSerializer(serializers.Serializer[None]):
    """Body for `POST /discounts:lookup-code`."""

    property_id = serializers.IntegerField(min_value=1)
    code = serializers.CharField(max_length=64)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    party = serializers.IntegerField(required=False, min_value=1)
