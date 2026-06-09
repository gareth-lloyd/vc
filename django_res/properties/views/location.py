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
        # none, so location-less rows need no separate backfill. The serializer
        # reads `location.country_id` (a plain PK), so no join is needed on the
        # common existing-row path; `region.country` is only walked by
        # `ensure_property_location` when it actually creates the default row.
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        return ensure_property_location(property_obj)
