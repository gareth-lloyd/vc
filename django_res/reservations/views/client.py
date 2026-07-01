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
from django.db.models import Exists, OuterRef, Q, QuerySet, Subquery
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as drf_filters
from rest_framework import generics

from accounts.enums import PersonKind
from accounts.models import Person
from core.api import IsStaff
from reservations.enums import QUOTED_STATUSES, UNREALISED_BOOKING_STATUSES
from reservations.filters import ClientFilterSet, client_agent_capacity_expression
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
        # `is_agent` (agent-capacity) is annotated for serialization and is the
        # same expression the membership filter and `capacity` filter key on
        # (`client_agent_capacity_expression`). `is_repeat_customer` is the
        # Repeat-chip flag. `quoted_/booked_region_slugs` are correlated ArrayAgg
        # subqueries (no JOIN, so they don't multiply rows or the paginator COUNT).
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
            # GAP-053: agents fold into Clients — membership is customers PLUS
            # agent-capacity people (belong to an agency, or deal via an agent),
            # not `kind=CUSTOMER` alone. Perf note: the OR can't be served by the
            # `kind` index alone, so non-customer rows evaluate the capacity EXISTS
            # battery. Acceptable while customers dominate the Person table (they
            # short-circuit on the indexed `kind=CUSTOMER` arm); if the directory
            # slows, denormalise an agent flag / add a partial index (deferred).
            Person.objects.filter(
                Q(kind=PersonKind.CUSTOMER) | Q(client_agent_capacity_expression())
            )
            .prefetch_related("emails", "phones")
            .annotate(
                is_agent=client_agent_capacity_expression(),
                # GAP-053: the "Repeat" chip's flag — >= 1 booking of ANY status,
                # via a scalar EXISTS (no JOIN → no COUNT inflation). Counts all
                # statuses to match ContactSerializer.is_repeat_customer (GAP-042),
                # so a person reads identically in /contacts and /clients. This is
                # a different axis from booked_region_slugs, which counts only
                # *realised* stays — a cancelled-only client is repeat=true here
                # with empty booked regions, by design.
                is_repeat_customer=Exists(Booking.objects.filter(person=OuterRef("pk"))),
                quoted_region_slugs=quoted,
                booked_region_slugs=booked,
            )
        )
