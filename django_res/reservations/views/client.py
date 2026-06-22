"""Clients (renter) directory list (GAP-047).

Hosted here, not in `accounts`: the list annotates over reservations deal
models (`Booking`/`Quotation`/`Enquiry`) to derive the booking-channel
`is_agent` flag, and `accounts` is the bottom of the import spine — a clean
downward reservations → accounts edge (precedent: `contact_reads.py`).

List-only: rows link to the existing `/contacts/{id}` detail until GAP-042
builds the customer-360 profile.
"""

from __future__ import annotations

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters as drf_filters
from rest_framework import generics

from accounts.enums import PersonKind
from accounts.models import Person
from core.api import IsStaff
from reservations.filters import ClientFilterSet, client_is_agent_expression
from reservations.serializers import ClientListSerializer


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
        return (
            Person.objects.filter(kind=PersonKind.CUSTOMER)
            .prefetch_related("emails", "phones")
            .annotate(is_agent=client_is_agent_expression())
        )
