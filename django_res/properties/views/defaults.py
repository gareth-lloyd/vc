"""`GET/PATCH /property-defaults` — the global creation-defaults singleton (GAP-070)."""

from __future__ import annotations

from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import PropertyDefaults
from properties.serializers import PropertyDefaultsSerializer


class PropertyDefaultsView(generics.RetrieveUpdateAPIView):
    serializer_class = PropertyDefaultsSerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> PropertyDefaults:
        return PropertyDefaults.get_solo()
