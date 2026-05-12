"""FilterSet for the property list endpoint."""

from __future__ import annotations

from django.db.models import Q, QuerySet
from django_filters import rest_framework as filters

from properties.models import Property


class PropertyFilter(filters.FilterSet):
    """Filters supported by `GET /properties`.

    Spec query params: `status`, `category`, `group`, `region`, `country`,
    `collection`, `min_bedrooms`, `max_bedrooms`, `min_guests`, `q`.
    """

    status = filters.CharFilter(field_name="status")
    category = filters.NumberFilter(field_name="category_id")
    group = filters.NumberFilter(field_name="group_id")
    region = filters.CharFilter(method="filter_region")
    country = filters.CharFilter(method="filter_country")
    collection = filters.CharFilter(method="filter_collection")
    min_bedrooms = filters.NumberFilter(field_name="capacity__bedrooms", lookup_expr="gte")
    max_bedrooms = filters.NumberFilter(field_name="capacity__bedrooms", lookup_expr="lte")
    min_guests = filters.NumberFilter(field_name="capacity__guests", lookup_expr="gte")
    q = filters.CharFilter(method="filter_q")

    class Meta:
        model = Property
        fields = [
            "status",
            "category",
            "group",
            "region",
            "country",
            "collection",
            "min_bedrooms",
            "max_bedrooms",
            "min_guests",
            "q",
        ]

    def filter_region(self, qs: QuerySet[Property], name: str, value: str) -> QuerySet[Property]:
        # Accept either a slug or a numeric id.
        if value.isdigit():
            return qs.filter(region_id=int(value))
        return qs.filter(region__slug=value)

    def filter_country(self, qs: QuerySet[Property], name: str, value: str) -> QuerySet[Property]:
        return qs.filter(region__country__iso2__iexact=value)

    def filter_collection(
        self, qs: QuerySet[Property], name: str, value: str
    ) -> QuerySet[Property]:
        if value.isdigit():
            return qs.filter(collections__id=int(value)).distinct()
        return qs.filter(collections__slug=value).distinct()

    def filter_q(self, qs: QuerySet[Property], name: str, value: str) -> QuerySet[Property]:
        return qs.filter(
            Q(name__icontains=value) | Q(display_name__icontains=value) | Q(slug__icontains=value)
        )
