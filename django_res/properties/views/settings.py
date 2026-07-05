"""View for `PropertySettings`.

Singleton-per-parent endpoints: `RetrieveUpdateAPIView` only.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import Property, PropertySettings
from properties.serializers import PropertySettingsSerializer


class PropertySettingsView(generics.RetrieveUpdateAPIView):
    serializer_class = PropertySettingsSerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> PropertySettings:
        # Join up front everything the serializer touches per GET/PATCH so no
        # field read fires an extra uncached SELECT:
        #   - `location` (reverse-OneToOne) for `property.location.timezone`;
        #   - `finance` for the commission/tax figures behind the GAP-035
        #     rate-entry derivation context.
        property_obj = get_object_or_404(
            Property.objects.select_related("location", "finance"),
            pk=self.kwargs["property_id"],
        )
        # `select_related("currency")` loads the `currency_code` projection
        # (GAP-026); reassigning `property` pins the prefetched chain above
        # onto the instance so neither read round-trips.
        instance, _ = PropertySettings.objects.select_related("currency").get_or_create(
            property=property_obj
        )
        instance.property = property_obj
        return instance
