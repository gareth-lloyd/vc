"""Serializers for `RatePlan` (Season), `RateCard`, and `RateRule`."""

from __future__ import annotations

from typing import Any

from django.db import models
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

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Mirror the RateRule DB constraints as 400s instead of 500s.

        Covers the four CHECK constraints plus the `raterule_no_overlap_same_priority`
        EXCLUDE constraint (inclusive date + party ranges). A missing key falls
        back to the stored instance value (PATCH) or the model default (create),
        so neither path can combine into a row the constraints would reject.
        """

        def effective(field: str) -> Any:
            if field in attrs:
                return attrs[field]
            if self.instance is not None:
                return getattr(self.instance, field)
            model_field = RateRule._meta.get_field(field)
            assert isinstance(model_field, models.Field)  # only concrete columns queried
            return model_field.get_default() if model_field.has_default() else None

        date_from, date_to = effective("date_from"), effective("date_to")
        if date_from is not None and date_to is not None and date_from >= date_to:
            raise serializers.ValidationError(
                {"date_to": "date_to must be after date_from."},
            )

        min_party, max_party = effective("min_party"), effective("max_party")
        if min_party is not None and max_party is not None and min_party > max_party:
            raise serializers.ValidationError(
                {"max_party": "max_party must be greater than or equal to min_party."},
            )

        nightly, weekly, is_poa = effective("nightly"), effective("weekly"), effective("is_poa")
        has_price = nightly is not None or weekly is not None
        if is_poa and has_price:
            raise serializers.ValidationError(
                {"is_poa": "A POA rule cannot also carry a nightly or weekly price."},
            )
        if not is_poa and not has_price:
            raise serializers.ValidationError(
                {"nightly": "Set a nightly or weekly price, or mark the rule POA."},
            )

        card = self._resolve_card(attrs)
        if card is not None and None not in (date_from, date_to, min_party, max_party):
            overlapping = RateRule.objects.filter(
                card=card,
                priority=effective("priority"),
                date_from__lte=date_to,
                date_to__gte=date_from,
                min_party__lte=max_party,
                max_party__gte=min_party,
            )
            if self.instance is not None:
                overlapping = overlapping.exclude(pk=self.instance.pk)
            clash = overlapping.first()
            if clash is not None:
                raise serializers.ValidationError(
                    {
                        "date_from": (
                            "Dates and party size overlap an existing rule "
                            f"({clash.date_from} to {clash.date_to}, "
                            f"party {clash.min_party}-{clash.max_party}). "
                            "Date ranges are inclusive: start the next rule "
                            "the day after the previous one ends."
                        ),
                    },
                )
        return attrs

    def _resolve_card(self, attrs: dict[str, Any]) -> RateCard | None:
        """The card comes from the body, the stored row, or the nested-create URL."""
        if attrs.get("card") is not None:
            return attrs["card"]
        if self.instance is not None:
            return self.instance.card
        view = self.context.get("view")
        card_id = getattr(view, "kwargs", {}).get("rate_card_id")
        if card_id is None:
            return None
        return RateCard.objects.filter(pk=card_id).first()


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
