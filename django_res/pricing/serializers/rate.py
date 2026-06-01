"""Serializers for `RatePlan` (Season), `RateCard`, and `RateRule`."""

from __future__ import annotations

from rest_framework import serializers

from pricing.models import RateCard, RatePlan, RateRule
from properties.models import Property


class RateRuleSerializer(serializers.ModelSerializer[RateRule]):
    card = serializers.PrimaryKeyRelatedField(
        queryset=RateCard.objects.all(),
        required=False,
    )

    class Meta:
        model = RateRule
        fields = [
            "id",
            "card",
            "date_from",
            "date_to",
            "min_party",
            "max_party",
            "priority",
            "nightly",
            "weekly",
            "is_poa",
            "is_locked",
            "is_approved",
            "notes",
        ]
        read_only_fields = ["id"]


class RateCardSerializer(serializers.ModelSerializer[RateCard]):
    rules = RateRuleSerializer(many=True, read_only=True)
    plan = serializers.PrimaryKeyRelatedField(
        queryset=RatePlan.objects.all(),
        required=False,
    )

    class Meta:
        model = RateCard
        fields = [
            "id",
            "plan",
            "name",
            "description",
            "min_nights",
            "max_nights",
            "changeover_weekday",
            "sort_order",
            "is_active",
            "notes",
            "rules",
        ]
        read_only_fields = ["id", "rules"]


class RatePlanSerializer(serializers.ModelSerializer[RatePlan]):
    """Lighter list shape — no nested cards/rules."""

    property = serializers.PrimaryKeyRelatedField(
        queryset=Property.objects.all(),
        required=False,
    )
    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = RatePlan
        fields = [
            "id",
            "property",
            "name",
            "currency",
            "currency_code",
            "price_basis",
            "fallback_nightly",
            "effective_from",
            "effective_to",
            "is_active",
            "notes",
            "inclusion",
        ]
        read_only_fields = ["id"]


class RatePlanDetailSerializer(RatePlanSerializer):
    """Full detail — inlines `cards` with their rules."""

    cards = RateCardSerializer(many=True, read_only=True)

    class Meta(RatePlanSerializer.Meta):
        fields = [*RatePlanSerializer.Meta.fields, "cards"]
        read_only_fields = [*RatePlanSerializer.Meta.read_only_fields, "cards"]
