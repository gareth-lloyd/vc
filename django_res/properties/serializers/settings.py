"""Serializers for `PropertySettings` and `GroupSettings`."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from properties.models import GroupSettings, PropertySettings


class PropertySettingsSerializer(serializers.ModelSerializer[PropertySettings]):
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
        ]
        read_only_fields = ["property"]

    def to_representation(self, instance: PropertySettings) -> dict[str, Any]:
        data = super().to_representation(instance)
        # `timezone` physically lives on `PropertyLocation` (a geographic fact
        # of the place, never inherited from the group). It is surfaced here
        # read-only for context beside the check-in/out times; the location
        # endpoint (`/properties/{id}/location`) is the sole writer.
        try:
            data["timezone"] = instance.property.location.timezone
        except ObjectDoesNotExist:
            data["timezone"] = None
        # `currency_code` (GAP-026): the group-resolved *effective* currency as a
        # string code, so money inputs can label which currency they commit to
        # without the client re-deriving the FK id or the inheritance chain. The
        # raw `currency` FK stays writable; this is its read-only display
        # projection. `None` when neither property nor group sets a currency.
        data["currency_code"] = self._effective_currency_code(instance)
        return data

    @staticmethod
    def _effective_currency_code(instance: PropertySettings) -> str | None:
        try:
            currency = instance.effective("currency")
        except ObjectDoesNotExist:
            # The group has no settings row, so the fallback leg is absent; only
            # the property-level value — null on this branch — applies.
            currency = instance.currency
        return currency.code if currency is not None else None


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
