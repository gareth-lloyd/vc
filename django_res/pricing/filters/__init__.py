"""Pricing FilterSets."""

from __future__ import annotations

from datetime import date

from django.db.models import QuerySet
from django_filters import rest_framework as filters

from pricing.models import Discount


class DiscountFilter(filters.FilterSet):
    property = filters.NumberFilter(field_name="property_id")
    rule_kind = filters.CharFilter(field_name="rule_kind")
    code = filters.CharFilter(field_name="code", lookup_expr="iexact")
    is_active = filters.BooleanFilter(field_name="is_active")
    valid_on = filters.CharFilter(method="filter_valid_on")

    class Meta:
        model = Discount
        fields = ["property", "rule_kind", "code", "is_active", "valid_on"]

    def filter_valid_on(self, qs: QuerySet[Discount], name: str, value: str) -> QuerySet[Discount]:
        try:
            day = date.fromisoformat(value)
        except ValueError:
            return qs.none()
        return qs.filter(valid_from__lte=day, valid_to__gte=day)
