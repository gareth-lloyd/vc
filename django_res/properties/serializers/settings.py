"""Serializers for `PropertySettings` and `GroupSettings`."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from rest_framework import serializers

from properties.models import GroupSettings, PropertySettings
from properties.services.location import ensure_property_location
from properties.timezones import validate_iana_timezone


class PropertySettingsSerializer(serializers.ModelSerializer[PropertySettings]):
    # `timezone` physically lives on `PropertyLocation` (a geographic fact of
    # the place, never inherited from the group), surfaced here so ops edit it
    # beside the check-in/out times it contextualises. Read is injected in
    # `to_representation`; write is applied to the location in `update`.
    timezone = serializers.CharField(
        validators=[validate_iana_timezone],
        required=False,
        write_only=True,
    )

    class Meta:
        model = PropertySettings
        fields = [
            "property",
            "availability_default",
            "bookings_require_pre_approval",
            "requires_enquiry_first",
            "currency",
            "check_in_time",
            "check_out_time",
            "changeover_day",
            "min_nights_rental",
            "min_nights_rental_note",
            "prices_entered_as",
            "timezone",
        ]
        read_only_fields = ["property"]

    def to_representation(self, instance: PropertySettings) -> dict[str, Any]:
        data = super().to_representation(instance)
        try:
            data["timezone"] = instance.property.location.timezone
        except ObjectDoesNotExist:
            data["timezone"] = None
        return data

    def update(
        self, instance: PropertySettings, validated_data: dict[str, Any]
    ) -> PropertySettings:
        timezone = validated_data.pop("timezone", None)
        with transaction.atomic():
            settings = super().update(instance, validated_data)
            if timezone is not None:
                # A property created outside migration/seed has no location yet;
                # provision a default one so its timezone is always editable.
                location = ensure_property_location(instance.property)
                if timezone != location.timezone:
                    location.timezone = timezone
                    location.save(update_fields=["timezone"])
        return settings


class GroupSettingsSerializer(serializers.ModelSerializer[GroupSettings]):
    class Meta:
        model = GroupSettings
        fields = [
            "group",
            "availability_default",
            "bookings_require_pre_approval",
            "requires_enquiry_first",
            "currency",
            "check_in_time",
            "check_out_time",
            "changeover_day",
            "min_nights_rental",
            "min_nights_rental_note",
            "prices_entered_as",
        ]
        read_only_fields = ["group"]
