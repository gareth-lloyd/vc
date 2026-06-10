"""Request shapes for the pricing helper endpoints."""

from __future__ import annotations

from rest_framework import serializers


class PricingQuoteRequestSerializer(serializers.Serializer[None]):
    """Body for `POST /pricing:quote`."""

    property_id = serializers.IntegerField(min_value=1)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    adults = serializers.IntegerField(min_value=1)
    children = serializers.IntegerField(required=False, default=0, min_value=0)
    # Optional (GAP-014): omitted means "price in the rate plan's own
    # currency"; supplying it keeps the explicit-currency exact match.
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True, default="")
    opt_in_extras = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )
    discount_code = serializers.CharField(required=False, allow_blank=True, default="")


class _BulkRequestEntrySerializer(serializers.Serializer[None]):
    property_id = serializers.IntegerField(min_value=1)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    adults = serializers.IntegerField(min_value=1)
    children = serializers.IntegerField(required=False, default=0, min_value=0)
    opt_in_extras = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        default=list,
    )


class PricingQuoteBulkRequestSerializer(serializers.Serializer[None]):
    """Body for `POST /pricing:quote-bulk`."""

    requests = _BulkRequestEntrySerializer(many=True, allow_empty=False)
    # Optional (GAP-014) — see PricingQuoteRequestSerializer.currency.
    currency = serializers.CharField(max_length=3, required=False, allow_blank=True, default="")
