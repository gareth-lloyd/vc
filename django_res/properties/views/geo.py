"""Viewsets for geo lookups + property-nested nearby POIs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.shortcuts import get_object_or_404
from rest_framework import generics, viewsets

from core.api import (
    AllowAnyReadStaffWrite,
    ConfigurablePageSizePagination,
    IsReservationsWriter,
)
from properties.models import (
    Country,
    NearbyPlaceType,
    Property,
    PropertyNearbyPlace,
    Region,
)
from properties.serializers import (
    CountrySerializer,
    NearbyPlaceTypeSerializer,
    PropertyNearbyPlaceSerializer,
    RegionSerializer,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet


class CountryViewSet(viewsets.ModelViewSet):
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    permission_classes = [AllowAnyReadStaffWrite]
    # The full ~250-row list is needed in one request to populate country
    # `<Select>`s (e.g. the property location form); allow a client page size.
    pagination_class = ConfigurablePageSizePagination
    lookup_field = "iso2"


class RegionViewSet(viewsets.ModelViewSet):
    queryset = Region.objects.all().select_related("country")
    serializer_class = RegionSerializer
    permission_classes = [AllowAnyReadStaffWrite]
    lookup_field = "slug"


class NearbyPlaceTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only — taxonomy is seeded via data migration."""

    queryset = NearbyPlaceType.objects.all()
    serializer_class = NearbyPlaceTypeSerializer
    permission_classes = [AllowAnyReadStaffWrite]


class PropertyNearbyPlaceListCreateView(generics.ListCreateAPIView):
    serializer_class = PropertyNearbyPlaceSerializer
    permission_classes = [IsReservationsWriter]

    def get_queryset(self) -> QuerySet[PropertyNearbyPlace]:
        return PropertyNearbyPlace.objects.filter(property_id=self.kwargs["property_id"])

    def perform_create(self, serializer: Any) -> None:
        property_obj = get_object_or_404(Property, pk=self.kwargs["property_id"])
        serializer.save(property=property_obj)


class PropertyNearbyPlaceDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertyNearbyPlaceSerializer
    permission_classes = [IsReservationsWriter]
    lookup_url_kwarg = "poi_id"

    def get_queryset(self) -> QuerySet[PropertyNearbyPlace]:
        return PropertyNearbyPlace.objects.filter(property_id=self.kwargs["property_id"])
