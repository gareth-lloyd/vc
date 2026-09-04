"""Viewsets for `Feature` and `FeatureCategory`."""

from __future__ import annotations

from django.db.models import QuerySet
from django_filters import rest_framework as filters
from rest_framework import viewsets

from core.api import AllowAnyReadStaffWrite, ConfigurablePageSizePagination
from properties.models import Feature, FeatureCategory
from properties.serializers import (
    FeatureCategorySerializer,
    FeatureSerializer,
)


class FeatureCategoryViewSet(viewsets.ModelViewSet):
    queryset = FeatureCategory.objects.all()
    serializer_class = FeatureCategorySerializer
    permission_classes = [AllowAnyReadStaffWrite]


class FeatureFilterSet(filters.FilterSet):
    """Filters supported by `GET /features`.

    `category` accepts either the category slug or its numeric id, mirroring
    `PropertyFilter.filter_region`'s id-or-slug convention.
    """

    category = filters.CharFilter(method="filter_category")

    class Meta:
        model = Feature
        fields = ["category"]

    def filter_category(self, qs: QuerySet[Feature], name: str, value: str) -> QuerySet[Feature]:
        if value.isdigit():
            return qs.filter(category_id=int(value))
        return qs.filter(category__slug=value)


class FeatureViewSet(viewsets.ModelViewSet):
    queryset = Feature.objects.all().select_related("category")
    serializer_class = FeatureSerializer
    permission_classes = [AllowAnyReadStaffWrite]
    filterset_class = FeatureFilterSet
    pagination_class = ConfigurablePageSizePagination
