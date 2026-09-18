"""GAP-117: cross-client list of legacy-imported stays — the "Imported bookings"
tab on the SPA's /bookings page.

`PastStay` rows are written only by the cutover importers (`import_past_bookers`,
`import_archive_stays`); an app-created `Booking` is never one, so it never
appears here. Read-only, staff-only, newest year first; `?search=` spans guest
name, villa and booking number.
"""

from __future__ import annotations

from django.db.models import F, QuerySet
from rest_framework import generics

from core.api import IsStaff
from reservations.models import PastStay
from reservations.serializers import PastStayListSerializer


class PastStayListView(generics.ListAPIView[PastStay]):
    """`GET /past-stays` — the UI's "Imported bookings" across all clients."""

    serializer_class = PastStayListSerializer
    permission_classes = [IsStaff]
    search_fields = [
        "person__first_name",
        "person__last_name",
        "villa_name",
        "property__name",
        "property__display_name",
        "booking_number",
    ]
    # Model Meta order only: an empty list stops the global OrderingFilter
    # accepting `?ordering=` on arbitrary serializer fields.
    ordering_fields: list[str] = []

    def get_queryset(self) -> QuerySet[PastStay]:
        # `PastStay.Meta.ordering` plus a `pk` tie-break: across clients many
        # rows share year / no dates / a blank or re-issued booking number, and
        # paging over a non-unique order can repeat or skip rows.
        return PastStay.objects.select_related("person", "property", "currency").order_by(
            F("year").desc(nulls_last=True),
            F("date_from").desc(nulls_last=True),
            "booking_number",
            "pk",
        )
