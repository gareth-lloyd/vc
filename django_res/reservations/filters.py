"""FilterSets for the reservations app collection endpoints."""

from __future__ import annotations

from typing import Any

from django.db.models import Exists, OuterRef, Q, QuerySet
from django.db.models.expressions import Combinable
from django_filters import rest_framework as filters

from accounts.models import Person, PersonEmail
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
    created_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    q = filters.CharFilter(method="filter_q")

    class Meta:
        model = Quotation
        fields = ["status", "enquiry", "created_after", "created_before", "q"]

    def filter_q(
        self, queryset: QuerySet[Quotation], _name: str, value: str
    ) -> QuerySet[Quotation]:
        if not value:
            return queryset
        # Mirrors BookingFilter.filter_q: customer search resolves from the
        # unified Person (GAP-045). `person__first_name`/`last_name` are
        # single-valued FK joins → safe in the OR. The person EMAIL lives in the
        # multi-valued PersonEmail child, so an OR'd join would multiply rows and
        # inflate the paginator COUNT (django_res/CLAUDE.md) — match it with a
        # scalar Exists() subquery, which adds no JOIN.
        person_email_match = PersonEmail.objects.filter(
            contact_id=OuterRef("person_id"), email__icontains=value
        )
        return queryset.filter(
            Q(reference__icontains=value)
            | Q(person__first_name__icontains=value)
            | Q(person__last_name__icontains=value)
            | Q(Exists(person_email_match))
        )


class BookingFilter(filters.FilterSet):
    """Filter shape for `GET /bookings`."""

    status = filters.CharFilter(field_name="status")
    property = filters.NumberFilter(field_name="property_id")
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
        # GAP-045 Unit 3d-3: customer search resolves solely from the unified
        # Person. `person__first_name`/`last_name` are single-valued FK joins →
        # safe in the OR. The person EMAIL lives in a multi-valued child table, so
        # an OR'd `person__emails__email` join would multiply rows and leak into
        # the paginator COUNT / StatusCountsMixin (django_res/CLAUDE.md). Match
        # it with a scalar `Exists()` subquery instead, which adds no JOIN.
        person_email_match = PersonEmail.objects.filter(
            contact_id=OuterRef("person_id"), email__icontains=value
        )
        return queryset.filter(
            Q(reference__icontains=value)
            | Q(person__first_name__icontains=value)
            | Q(person__last_name__icontains=value)
            | Q(Exists(person_email_match))
            | Q(property__name__icontains=value)
        )


def client_is_agent_expression() -> Combinable:
    """Boolean expression: the client (`Person`) has any deal that names a
    travel agent — the "agent" booking channel (GAP-047).

    Scalar `EXISTS` per relation (no JOIN row-multiplication, so a paginator
    COUNT over it stays honest), OR'd into one boolean. The single source of
    truth shared by `ClientListView`'s `is_agent` annotation and
    `ClientFilterSet.capacity` so the two can't drift.
    """
    agent_deal = {"person": OuterRef("pk"), "agent__isnull": False}
    return (
        Exists(Booking.objects.filter(**agent_deal))
        | Exists(Quotation.objects.filter(**agent_deal))
        | Exists(Enquiry.objects.filter(**agent_deal))
    )


class ClientFilterSet(filters.FilterSet):
    """Filter shape for `GET /clients` (GAP-047).

    `capacity` partitions the directory by booking channel — `agent` (the client
    has an enquiry/quote/booking that names a travel agent) vs `direct`.
    """

    status = filters.CharFilter(field_name="status")
    capacity = filters.ChoiceFilter(
        method="filter_capacity",
        choices=[("direct", "Direct"), ("agent", "Agent")],
    )

    class Meta:
        model = Person
        fields = ["status", "capacity"]

    def filter_capacity(
        self, queryset: QuerySet[Person], _name: str, value: str
    ) -> QuerySet[Person]:
        if value not in ("agent", "direct"):
            return queryset
        is_agent = Q(client_is_agent_expression())
        return queryset.filter(is_agent if value == "agent" else ~is_agent)
