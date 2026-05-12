"""Viewsets for `PropertyCategory` and `PropertyGroup`."""

from __future__ import annotations

from rest_framework import viewsets

from core.api import AllowAnyReadStaffWrite, IsReservationsWriter
from properties.models import PropertyCategory, PropertyGroup
from properties.serializers import (
    PropertyCategorySerializer,
    PropertyGroupSerializer,
)


class PropertyCategoryViewSet(viewsets.ModelViewSet):
    queryset = PropertyCategory.objects.all()
    serializer_class = PropertyCategorySerializer
    permission_classes = [AllowAnyReadStaffWrite]


class PropertyGroupViewSet(viewsets.ModelViewSet):
    queryset = PropertyGroup.objects.all()
    serializer_class = PropertyGroupSerializer
    permission_classes = [IsReservationsWriter]
