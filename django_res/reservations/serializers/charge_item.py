"""Charge line-item serializers."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from reservations.models import BookingChargeItem


class BookingChargeItemSerializer(serializers.ModelSerializer[BookingChargeItem]):
    """Read representation."""

    currency_code = serializers.CharField(source="currency.code", read_only=True)

    class Meta:
        model = BookingChargeItem
        fields = [
            "id",
            "booking",
            "label",
            "amount",
            "currency",
            "currency_code",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "booking", "created_at", "updated_at"]


class BookingChargeItemWriteSerializer(serializers.ModelSerializer[BookingChargeItem]):
    """Write body. `currency` is optional — the service defaults it to the
    booking's and rejects a mismatch."""

    class Meta:
        model = BookingChargeItem
        fields = [
            "label",
            "amount",
            "currency",
            "notes",
        ]
        extra_kwargs = {"currency": {"required": False}}

    def validate_amount(self, value: Decimal) -> Decimal:
        # Surface the model's non-zero check constraint as a 400 field error
        # instead of a 500 IntegrityError.
        if value == 0:
            raise serializers.ValidationError("Amount must not be zero.")
        return value
