"""Concierge line-item serializers."""

from __future__ import annotations

from rest_framework import serializers

from reservations.models import BookingConciergeItem


class BookingConciergeItemSerializer(serializers.ModelSerializer[BookingConciergeItem]):
    """Read representation."""

    class Meta:
        model = BookingConciergeItem
        fields = [
            "id",
            "booking",
            "tier",
            "name",
            "description",
            "quantity",
            "unit",
            "unit_price",
            "currency",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "booking", "created_at", "updated_at"]


class BookingConciergeItemWriteSerializer(serializers.ModelSerializer[BookingConciergeItem]):
    """Write body. `status` is action-driven via :confirm."""

    class Meta:
        model = BookingConciergeItem
        fields = [
            "tier",
            "name",
            "description",
            "quantity",
            "unit",
            "unit_price",
            "currency",
            "notes",
        ]
