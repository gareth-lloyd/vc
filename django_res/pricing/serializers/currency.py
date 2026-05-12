"""Serializers for `Currency` and `FxRate`."""

from __future__ import annotations

from rest_framework import serializers

from pricing.models import Currency, FxRate


class CurrencySerializer(serializers.ModelSerializer[Currency]):
    class Meta:
        model = Currency
        fields = ["id", "code", "name", "symbol", "decimal_places", "is_active"]
        read_only_fields = ["id"]


class FxRateSerializer(serializers.ModelSerializer[FxRate]):
    class Meta:
        model = FxRate
        fields = ["id", "base", "quote", "rate", "as_of"]
        read_only_fields = ["id"]
