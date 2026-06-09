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
        # Join the reverse-OneToOne `location` up front: the serializer reads
        # `property.location.timezone` on every GET/PATCH, which would otherwise
        # fire one extra uncached SELECT per request.
        property_obj = get_object_or_404(
            Property.objects.select_related("location"), pk=self.kwargs["property_id"]
        )
        instance, _ = PropertySettings.objects.get_or_create(property=property_obj)
        return instance


class GroupSettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = GroupSettingsSerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> GroupSettings:
        group = get_object_or_404(PropertyGroup, pk=self.kwargs["group_id"])
        instance, _ = GroupSettings.objects.get_or_create(group=group)
        return instance
