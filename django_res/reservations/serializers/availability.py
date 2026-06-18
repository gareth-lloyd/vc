"""Serializers for the availability surface.

Availability writes back `BookingHold` rows (manual blocks, owner blocks).
The on-the-wire shape is intentionally distinct from BookingHold's
internals — it speaks "availability" not "hold".
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from reservations.enums import OPERATOR_EDITABLE_HOLD_REASONS, BookingHoldReason
from reservations.models.booking import Booking, BookingHold
from reservations.serializers._contact_reads import contact_name

_EDITABLE_CHOICES = [
    choice for choice in BookingHoldReason.choices if choice[0] in OPERATOR_EDITABLE_HOLD_REASONS
]


class AvailabilityWriteSerializer(serializers.Serializer[None]):
    """Body for `POST /properties/{id}/availability` — write a block."""

    date_from = serializers.DateField()
    date_to = serializers.DateField()
    reason = serializers.ChoiceField(
        choices=_EDITABLE_CHOICES,
        default=BookingHoldReason.MANUAL.value,
    )
    expires_at = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["date_to"] <= attrs["date_from"]:
            raise serializers.ValidationError({"date_to": "`date_to` must be after `date_from`."})
        return attrs


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
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class AvailabilityBookingSerializer(serializers.ModelSerializer["Booking"]):
    """Booking band for the multi-villa timeline (`GET /availability`).

    Deliberately light: enough to paint a band and label its popover. The
    booking detail endpoint carries the rest.
    """

    guest_name = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "property",
            "date_from",
            "date_to",
            "status",
            "reference",
            "guest_name",
        ]

    def get_guest_name(self, obj: Booking) -> str | None:
        return contact_name(obj.person, obj.guest)


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
