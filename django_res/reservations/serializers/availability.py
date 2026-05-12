"""Serializers for the availability surface.

Availability writes back `BookingHold` rows (manual blocks, owner blocks).
The on-the-wire shape is intentionally distinct from BookingHold's
internals — it speaks "availability" not "hold".
"""

from __future__ import annotations

from rest_framework import serializers

from reservations.enums import BookingHoldReason
from reservations.models.booking import BookingHold


class AvailabilityWriteSerializer(serializers.Serializer[None]):
    """Body for `POST /properties/{id}/availability` — write a block."""

    date_from = serializers.DateField()
    date_to = serializers.DateField()
    reason = serializers.ChoiceField(
        choices=BookingHoldReason.choices,
        default=BookingHoldReason.MANUAL.value,
    )
    expires_at = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class AvailabilityRecordSerializer(serializers.ModelSerializer[BookingHold]):
    """Read shape for a single availability record (backed by `BookingHold`)."""

    class Meta:
        model = BookingHold
        fields = [
            "id",
            "property",
            "date_from",
            "date_to",
            "expires_at",
            "released_at",
            "reason",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AvailabilitySearchSerializer(serializers.Serializer[None]):
    """Body for `POST /availability:search`."""

    date_from = serializers.DateField()
    date_to = serializers.DateField()
    adults = serializers.IntegerField(min_value=1)
    children = serializers.IntegerField(required=False, default=0, min_value=0)
    filters = serializers.DictField(required=False, default=dict)


class AvailabilityBulkBlockSerializer(serializers.Serializer[None]):
    """Body for `POST /availability:bulk-block`."""

    property_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    reason = serializers.ChoiceField(
        choices=BookingHoldReason.choices,
        default=BookingHoldReason.OWNER_BLOCK.value,
    )
    expires_at = serializers.DateTimeField(required=False)


class AvailabilityExtendHoldSerializer(serializers.Serializer[None]):
    expires_at = serializers.DateTimeField()
