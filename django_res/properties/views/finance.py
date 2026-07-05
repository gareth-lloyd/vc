"""View for `PropertyFinance` (one row per property)."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import Property, PropertyFinance
from properties.serializers import PropertyFinanceSerializer


class PropertyFinanceView(generics.RetrieveUpdateAPIView):
    serializer_class = PropertyFinanceSerializer
    permission_classes = [IsReservationsWriter]

    def get_object(self) -> PropertyFinance:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        instance, _ = PropertyFinance.objects.get_or_create(property=property_obj)
        return instance
