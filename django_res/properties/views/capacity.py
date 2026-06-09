"""View for `PropertyCapacity` (one row per property)."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import Property, PropertyCapacity
from properties.serializers import PropertyCapacitySerializer


class PropertyCapacityView(generics.RetrieveUpdateAPIView):
    serializer_class = PropertyCapacitySerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> PropertyCapacity:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        instance, _ = PropertyCapacity.objects.get_or_create(property=property_obj)
        return instance
