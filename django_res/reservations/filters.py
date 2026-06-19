"""FilterSets for the reservations app collection endpoints."""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet
from django_filters import rest_framework as filters

from reservations.enums import TERMINAL_BOOKING_STATUSES
from reservations.models import Booking, Enquiry, Quotation


class EnquiryFilter(filters.FilterSet):
    """Filter shape for `GET /enquiries`."""

    status = filters.CharFilter(field_name="status")
    lead_status = filters.CharFilter(field_name="lead_status")
    lost_reason = filters.CharFilter(field_name="lost_reason")
    site = filters.CharFilter(field_name="site_source")
    assigned_to = filters.CharFilter(method="filter_assigned_to")
    source = filters.CharFilter(field_name="site_source")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    q = filters.CharFilter(method="filter_q")

    class Meta:
        model = Enquiry
        fields = [
            "status",
            "lead_status",
            "lost_reason",
            "site",
            "assigned_to",
            "source",
            "created_after",
            "created_before",
            "q",
        ]

    def filter_assigned_to(
        self, queryset: QuerySet[Enquiry], _name: str, value: str
    ) -> QuerySet[Enquiry]:
        """Salesperson filter: a numeric user id (exact), or the `unassigned`
        sentinel for IS NULL (the dashboard's "— Unassigned —" option, which a
        plain NumberFilter can't express). Anything else is ignored."""
        if not value:
            return queryset
        if value == "unassigned":
            return queryset.filter(assigned_to__isnull=True)
        if value.isdigit():
            return queryset.filter(assigned_to_id=int(value))
        return queryset

    def filter_q(self, queryset: QuerySet[Enquiry], _name: str, value: str) -> QuerySet[Enquiry]:
        if not value:
            return queryset
        return queryset.filter(
            Q(reference__icontains=value)
            | Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(email__icontains=value)
            | Q(inbound_message__icontains=value)
        )


class QuotationFilter(filters.FilterSet):
    """Filter shape for `GET /quotations`."""

    status = filters.CharFilter(field_name="status")
    enquiry = filters.NumberFilter(field_name="enquiry_id")
    guest = filters.NumberFilter(field_name="guest_id")
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Quotation
        fields = ["status", "enquiry", "guest", "created_after", "created_before"]


class BookingFilter(filters.FilterSet):
    """Filter shape for `GET /bookings`."""

    status = filters.CharFilter(field_name="status")
    property = filters.NumberFilter(field_name="property_id")
    guest = filters.NumberFilter(field_name="guest_id")
    assigned_to = filters.NumberFilter(field_name="assigned_to_id")
    site = filters.CharFilter(field_name="site_source")
    check_in_after = filters.DateFilter(field_name="date_from", lookup_expr="gte")
    check_in_before = filters.DateFilter(field_name="date_from", lookup_expr="lte")
    check_out_after = filters.DateFilter(field_name="date_to", lookup_expr="gte")
    check_out_before = filters.DateFilter(field_name="date_to", lookup_expr="lte")
    exclude_terminal = filters.BooleanFilter(method="filter_exclude_terminal")
    q = filters.CharFilter(method="filter_q")

    class Meta:
        model = Booking
        fields: list[Any] = [
            "status",
            "property",
            "guest",
            "assigned_to",
            "site",
            "check_in_after",
            "check_in_before",
            "check_out_after",
            "check_out_before",
            "exclude_terminal",
            "q",
        ]

    def filter_exclude_terminal(
        self, queryset: QuerySet[Booking], _name: str, value: bool
    ) -> QuerySet[Booking]:
        if not value:
            return queryset
        return queryset.exclude(status__in=TERMINAL_BOOKING_STATUSES)

    def filter_q(self, queryset: QuerySet[Booking], _name: str, value: str) -> QuerySet[Booking]:
        if not value:
            return queryset
        return queryset.filter(
            Q(reference__icontains=value)
            | Q(guest__first_name__icontains=value)
            | Q(guest__last_name__icontains=value)
            | Q(guest__email__icontains=value)
            | Q(property__name__icontains=value)
        )
