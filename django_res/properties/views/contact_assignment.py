"""Views for the property-side of contact assignments."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics

from core.api import IsReservationsWriter
from properties.models import Property, PropertyContactAssignment
from properties.serializers import PropertyContactAssignmentSerializer

if TYPE_CHECKING:
    from django.db.models import QuerySet


class PropertyContactAssignmentListCreateView(generics.ListCreateAPIView):
    serializer_class = PropertyContactAssignmentSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[PropertyContactAssignment]:
        return PropertyContactAssignment.objects.filter(
            property_id=self.kwargs["property_id"]
        ).select_related("contact", "organisation")

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)


class PropertyContactAssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertyContactAssignmentSerializer
    permission_classes = [IsReservationsWriter]
    lookup_url_kwarg = "mapping_id"

    def get_queryset(self) -> QuerySet[PropertyContactAssignment]:
        return PropertyContactAssignment.objects.filter(
            property_id=self.kwargs["property_id"]
        ).select_related("contact", "organisation")
