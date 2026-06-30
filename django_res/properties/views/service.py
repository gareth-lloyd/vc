"""Views for `PropertyService` (GAP-037)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import Property
from properties.models.services import PropertyService
from properties.serializers.service import PropertyServiceSerializer

if TYPE_CHECKING:
    from django.db.models import QuerySet


class PropertyServiceListCreateView(generics.ListCreateAPIView):
    serializer_class = PropertyServiceSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[PropertyService]:
        return PropertyService.objects.filter(property_id=self.kwargs["property_id"])

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)


class PropertyServiceDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = PropertyService.objects.all()
    serializer_class = PropertyServiceSerializer
    permission_classes = [IsReservationsWriter]
