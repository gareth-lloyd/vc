"""FilterSets for the country/region lookup list endpoints."""

from __future__ import annotations

from django.db.models import QuerySet
from django_filters import rest_framework as filters

from properties.models import Country, Region


class CountryFilter(filters.FilterSet):
    """Filters supported by `GET /countries`.

    `has_properties=true` narrows the ISO-3166 seed to countries that actually
    hold properties, so filter dropdowns don't offer ~249 dead options. The
    param is opt-in narrowing only: `false` (or absent) is a no-op returning
    the full list, not a complement selector for property-less rows.
    """

    has_properties = filters.BooleanFilter(method="filter_has_properties")

    class Meta:
        model = Country
        fields = ["has_properties"]

    def filter_has_properties(
        self, qs: QuerySet[Country], name: str, value: bool
    ) -> QuerySet[Country]:
        if not value:
            return qs
        return qs.filter(regions__properties__isnull=False).distinct()


class RegionFilter(filters.FilterSet):
    """Filters supported by `GET /regions` (same rationale as CountryFilter).

    `country` (FK id) / `country_iso2` (case-insensitive, matching the iexact
    iso2 lookups elsewhere) scope the list to one country so pickers never
    offer impossible country+region combinations. `country` is a NumberFilter,
    not the auto-generated ModelChoiceFilter: a stale id (countries hard-delete
    under `merge_country`) should yield an empty list, not a 400.
    """

    has_properties = filters.BooleanFilter(method="filter_has_properties")
    country = filters.NumberFilter(field_name="country_id")
    country_iso2 = filters.CharFilter(field_name="country__iso2", lookup_expr="iexact")

    class Meta:
        model = Region
        fields = ["country", "has_properties"]

    def filter_has_properties(
        self, qs: QuerySet[Region], name: str, value: bool
    ) -> QuerySet[Region]:
        if not value:
            return qs
        return qs.filter(properties__isnull=False).distinct()
