"""View for `PropertyLocation` (singleton-per-property subresource)."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import Property, PropertyLocation
from properties.serializers import PropertyLocationSerializer
from properties.services.location import ensure_property_location


class PropertyLocationView(generics.RetrieveUpdateAPIView):
    serializer_class = PropertyLocationSerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> PropertyLocation:
        # A GET lazily provisions a default location for properties that have
        # none (the same heal as the settings endpoint), so location-less rows
        # need no separate backfill. `select_related("country")` keeps the
        # serializer's FK read on the join.
        property_obj = get_object_or_404(
            Property.objects.select_related("region__country"),
            pk=self.kwargs["property_id"],
        )
        return ensure_property_location(property_obj)
