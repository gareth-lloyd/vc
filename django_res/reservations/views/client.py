"""Clients (renter) directory list (GAP-047).

Hosted here, not in `accounts`: the list annotates over reservations deal
models (`Booking`/`Quotation`/`Enquiry`) to derive the booking-channel
`is_agent` flag, and `accounts` is the bottom of the import spine — a clean
downward reservations → accounts edge (precedent: `contact_reads.py`).

List-only: rows link to the existing `/contacts/{id}` detail until GAP-042
builds the customer-360 profile.
"""

from __future__ import annotations

from typing import Any

from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import OuterRef, QuerySet, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as drf_filters
from rest_framework import generics

from accounts.enums import PersonKind
from accounts.models import Person
from core.api import IsStaff
from reservations.enums import QUOTED_STATUSES, UNREALISED_BOOKING_STATUSES
from reservations.filters import ClientFilterSet, client_is_agent_expression
from reservations.models import Booking, QuotationLine
from reservations.serializers import ClientListSerializer


def _region_slugs_subquery(queryset: QuerySet[Any], group_field: str) -> Subquery:
    """Correlated `ArrayAgg` of distinct region slugs for one client.

    `queryset` is already filtered to the client's "real" deals (status-gated)
    and correlated via `OuterRef("pk")`. Grouping by the client FK (`group_field`)
    collapses the rows to a single array; an empty group yields no row, so the
    `Subquery` returns NULL — the serializer coalesces that to `[]`.
    """
    return Subquery(
        queryset.order_by()
        .values(group_field)
        .annotate(slugs=ArrayAgg("property__region__slug", distinct=True))
        .values("slugs")
    )


class ClientListView(generics.ListAPIView[Person]):
    """`GET /clients` — query-pinned renter directory over `accounts.Person`."""

    serializer_class = ClientListSerializer
    permission_classes = [IsStaff]
    filter_backends = [
        DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter,
    ]
    filterset_class = ClientFilterSet
    search_fields = ["first_name", "last_name", "emails__email"]
    ordering_fields = ["last_name", "first_name", "created_at"]
    ordering = ["last_name", "first_name"]

    def get_queryset(self) -> QuerySet[Person]:
        # `is_agent` (booking channel) is annotated for serialization; the
        # `capacity` filter keys on the same expression (`client_is_agent_expression`).
        # `quoted_/booked_region_slugs` are correlated ArrayAgg subqueries (no
        # JOIN, so they don't multiply rows or the paginator COUNT).
        quoted = _region_slugs_subquery(
            QuotationLine.objects.filter(
                quotation__person=OuterRef("pk"),
                quotation__status__in=QUOTED_STATUSES,
            ).exclude(
                quotation__legacy_id__startswith="booking-"
            ),  # CLAUDE.md: drop synthetic fills
            "quotation__person",
        )
        booked = _region_slugs_subquery(
            Booking.objects.filter(person=OuterRef("pk")).exclude(
                status__in=UNREALISED_BOOKING_STATUSES
            ),
            "person",
        )
        return (
            Person.objects.filter(kind=PersonKind.CUSTOMER)
            .prefetch_related("emails", "phones")
            .annotate(
                is_agent=client_is_agent_expression(),
                quoted_region_slugs=quoted,
                booked_region_slugs=booked,
            )
        )
