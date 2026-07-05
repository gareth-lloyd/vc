"""Viewset for `PropertyCategory`."""

from __future__ import annotations

from rest_framework import viewsets

from core.api import AllowAnyReadStaffWrite
from properties.models import PropertyCategory
from properties.serializers import PropertyCategorySerializer


class PropertyCategoryViewSet(viewsets.ModelViewSet):
    queryset = PropertyCategory.objects.all()
    serializer_class = PropertyCategorySerializer
    permission_classes = [AllowAnyReadStaffWrite]
