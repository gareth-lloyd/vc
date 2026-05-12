"""Viewsets for `Feature` and `FeatureCategory`."""

from __future__ import annotations

from rest_framework import viewsets

from core.api import AllowAnyReadStaffWrite
from properties.models import Feature, FeatureCategory
from properties.serializers import (
    FeatureCategorySerializer,
    FeatureSerializer,
)


class FeatureCategoryViewSet(viewsets.ModelViewSet):
    queryset = FeatureCategory.objects.all()
    serializer_class = FeatureCategorySerializer
    permission_classes = [AllowAnyReadStaffWrite]


class FeatureViewSet(viewsets.ModelViewSet):
    queryset = Feature.objects.all().select_related("category")
    serializer_class = FeatureSerializer
    permission_classes = [AllowAnyReadStaffWrite]
