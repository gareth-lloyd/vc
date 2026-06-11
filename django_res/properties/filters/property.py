"""FilterSet for the property list endpoint."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from django.db.models import F, Q, QuerySet
from django.db.models.functions import Coalesce
from django_filters import rest_framework as filters

from properties.enums import PrefilledChangeOverDay
from properties.models import Property


class PropertyFilter(filters.FilterSet):
    """Filters supported by `GET /properties`.

    Spec query params: `status`, `category`, `group`, `region`, `country`,
    `collection`, `min_bedrooms`, `max_bedrooms`, `min_guests`, `q`,
    `changeover_day`, `date_from`, `date_to`, `include_unavailable`.
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

    # T2.2 — search filtered to a specific weekday must also match properties
    # whose effective `changeover_day=ANY` (group-fallback aware).
    changeover_day = filters.ChoiceFilter(
        method="filter_changeover_day",
        choices=PrefilledChangeOverDay.choices,
    )

    # T3.1 — availability window. `date_from` + `date_to` activate the
    # availability filter; `include_unavailable=true` opts back into the full
    # set. Without a date range the filter is a no-op.
    date_from = filters.DateFilter(method="filter_noop")
    date_to = filters.DateFilter(method="filter_noop")
    include_unavailable = filters.BooleanFilter(method="filter_noop")

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
            "changeover_day",
            "date_from",
            "date_to",
            "include_unavailable",
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

    def filter_changeover_day(
        self, qs: QuerySet[Property], name: str, value: str
    ) -> QuerySet[Property]:
        """Match the requested weekday OR a property whose effective changeover
        day is `ANY`.

        Effective value resolves `PropertySettings.changeover_day` with fallback
        to the group's `GroupSettings.changeover_day` (which is non-null with
        default `ANY`), mirroring `PropertySettings.effective("changeover_day")`.
        """
        any_value = PrefilledChangeOverDay.ANY.value
        return qs.annotate(
            effective_changeover_day=Coalesce(
                F("settings__changeover_day"),
                F("group__settings__changeover_day"),
            ),
        ).filter(
            Q(effective_changeover_day=any_value) | Q(effective_changeover_day=value),
        )

    def filter_noop(self, qs: QuerySet[Property], name: str, value: object) -> QuerySet[Property]:
        """Availability params are applied as one bulk step in `filter_queryset`.

        Per-field methods would either re-run the unavailability query for each
        param or build it from a partial view of `request.GET`; the FilterSet
        override below resolves it once after the field-level filters run.
        """
        return qs

    def filter_queryset(self, queryset: QuerySet[Property]) -> QuerySet[Property]:
        queryset = super().filter_queryset(queryset)
        return self._apply_availability_filter(queryset)

    def _apply_availability_filter(self, queryset: QuerySet[Property]) -> QuerySet[Property]:
        """T3.1 — exclude properties with overlapping active bookings or live
        holds across the requested date range. No-op when either date is
        missing or `include_unavailable=true`.
        """
        date_range = parse_availability_range(self.data)
        if date_range is None or include_unavailable_requested(self.data):
            return queryset

        unavailable_ids = unavailable_property_ids(*date_range)
        if not unavailable_ids:
            return queryset
        return queryset.exclude(id__in=unavailable_ids)


def parse_availability_range(params: Mapping[str, object]) -> tuple[date, date] | None:
    """The single definition of "a valid availability date range".

    Shared by `PropertyFilter._apply_availability_filter` (row exclusion) and
    `PropertyViewSet.get_serializer_context` (per-row flag), so the two can
    never disagree on whether a request carries a date range.
    """
    date_from = _parse_date(params.get("date_from"))
    date_to = _parse_date(params.get("date_to"))
    if date_from is None or date_to is None or date_from >= date_to:
        return None
    return date_from, date_to


def include_unavailable_requested(params: Mapping[str, object]) -> bool:
    value = params.get("include_unavailable")
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def unavailable_property_ids(date_from: date, date_to: date) -> set[int]:
    """Bulk-query the unavailable property-id set for a date range.

    One query each for blocking bookings and live holds — both flat
    set-membership reads that scale with the number of conflicts, not with the
    number of properties under consideration. The result is fed straight into
    `.exclude(id__in=…)` so the main property query stays a single round-trip.

    Both predicates are the canonical model-layer ones
    (`Booking.objects.occupying` / `BookingHold.live_overlapping`), shared
    verbatim with the availability calendar so search and calendar can never
    drift on which bookings/holds occupy a range. The cross-app import is kept
    lazy inside the function — `properties → reservations` is a blessed
    catalogue-search seam (see the import-linter contract), not an app-load edge.
    """
    from reservations.models.booking import Booking, BookingHold

    booked_ids = Booking.objects.occupying(
        date_from=date_from,
        date_to=date_to,
    ).values_list("property_id", flat=True)

    held_ids = BookingHold.live_overlapping(
        date_from=date_from,
        date_to=date_to,
    ).values_list("property_id", flat=True)

    return {*booked_ids, *held_ids}
