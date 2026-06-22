"""Views for `PropertySettings` and `GroupSettings`.

Singleton-per-parent endpoints: `RetrieveUpdateAPIView` only.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import GroupSettings, Property, PropertyGroup, PropertySettings
from properties.serializers import GroupSettingsSerializer, PropertySettingsSerializer


class PropertySettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = PropertySettingsSerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> PropertySettings:
        # Join up front everything the serializer touches per GET/PATCH so no
        # field read fires an extra uncached SELECT:
        #   - `location` (reverse-OneToOne) for `property.location.timezone`;
        #   - `group__settings__currency` for the group-fallback leg of
        #     `effective("currency")` (GAP-026 `currency_code`) — `group__settings`
        #     also covers `effective("prices_entered_as")` (GAP-035);
        #   - `finance` + `group__finance` for the property → group commission/tax
        #     resolution behind the GAP-035 rate-entry derivation context.
        property_obj = get_object_or_404(
            Property.objects.select_related(
                "location",
                "group__settings__currency",
                "finance",
                "group__finance",
            ),
            pk=self.kwargs["property_id"],
        )
        # `select_related("currency")` loads the property-level leg of
        # `effective("currency")`; reassigning `property` pins the prefetched
        # chain above onto the instance so neither read round-trips.
        instance, _ = PropertySettings.objects.select_related("currency").get_or_create(
            property=property_obj
        )
        instance.property = property_obj
        return instance


class GroupSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = GroupSettingsSerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> GroupSettings:
        group = get_object_or_404(PropertyGroup, pk=self.kwargs["group_id"])
        instance, _ = GroupSettings.objects.get_or_create(group=group)
        return instance
