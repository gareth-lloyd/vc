"""Owner-portal booking-backed endpoints.

These live in `reservations` (not `owners`) because they read
`reservations.Booking`: the import spine runs reservations → owners, so a
reservations view may import `owners.scoping` / `owners.permissions` downward,
but `owners` may not reach up to Booking. Property/identity-only owner views
stay in the `owners` app.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from django.db.models import Count, Exists, OuterRef, Sum
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from owners.permissions import IsOwner
from owners.scoping import owner_property_ids, owner_visibility_map
from properties.models import Property
from reservations.enums import BookingStatus
from reservations.models import Booking
from reservations.serializers.owner import (
    OwnerBookingDetailSerializer,
    OwnerBookingListSerializer,
)
from reservations.services.owner_finance import owner_money_from_snapshot

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from rest_framework.request import Request

    from accounts.models import User

# Excluded from owner KPIs: drafts never confirmed and the dead-end states.
# CHECKED_OUT is kept — a completed stay is real revenue.
_NON_COUNTING_STATUSES = (
    BookingStatus.DRAFT.value,
    BookingStatus.CANCELLED.value,
    BookingStatus.EXPIRED.value,
    BookingStatus.DECLINED.value,
)
_UPCOMING_WINDOW_DAYS = 30
_UPCOMING_LIMIT = 5


class OwnerDashboardView(APIView):
    """`GET /owner/dashboard` — cheap KPI aggregates over the scoped bookings.

    Money figures ("your share" net) render only for properties the caller's
    org has a `view_full_money` grant on; with no such grant the net is null.
    Deferred KPIs (next payout, utilisation %) are intentionally omitted.
    """

    permission_classes = [IsOwner]

    def get(self, request: Request) -> Response:
        user = cast("User", request.user)
        property_ids = owner_property_ids(user)
        visibility = owner_visibility_map(user)
        today = timezone.localdate()
        year_start = date(today.year, 1, 1)

        scoped = Booking.objects.filter(property_id__in=property_ids).exclude(
            status__in=_NON_COUNTING_STATUSES
        )
        ytd = scoped.filter(date_from__gte=year_start, date_from__lte=today)
        # Booking count is operational, not financial — always shown.
        bookings_count = ytd.count()

        # Both money KPIs are gated to view_full_money properties: gross revenue
        # is as sensitive as the per-booking rental_price the booking endpoint
        # redacts (for a single booking the sum *is* that price). With no
        # full-money grant, both stay null rather than leaking via aggregation.
        full_money_ids = {pid for pid, flags in visibility.items() if flags["view_full_money"]}
        gross: Decimal | None = None
        net_to_owner: Decimal | None = None
        if full_money_ids:
            money_ytd = ytd.filter(property_id__in=full_money_ids)
            gross = money_ytd.aggregate(total=Sum("rental_price"))["total"] or Decimal("0")
            net_to_owner = Decimal("0")
            for snapshot in money_ytd.values_list("pricing_snapshot", flat=True):
                money = owner_money_from_snapshot(snapshot)
                if money is not None:
                    net_to_owner += money["net_to_owner"]

        by_status = {
            row["status"]: row["count"]
            for row in Property.objects.filter(id__in=property_ids)
            .values("status")
            .annotate(count=Count("id"))
        }

        upcoming = (
            scoped.filter(
                date_from__gte=today,
                date_from__lte=today + timedelta(days=_UPCOMING_WINDOW_DAYS),
            )
            .select_related("property", "guest")
            .order_by("date_from")[:_UPCOMING_LIMIT]
        )
        upcoming_payload = [
            {
                "reference": booking.reference,
                "property_id": booking.property_id,
                "property_name": booking.property.name if booking.property_id else None,
                "date_from": booking.date_from,
                "date_to": booking.date_to,
                # Named, contact withheld — the owner redaction policy.
                "guest_name": (
                    f"{booking.guest.first_name} {booking.guest.last_name}".strip()
                    if booking.guest_id
                    else None
                ),
                "adults": booking.adults,
                "children": booking.children,
            }
            for booking in upcoming
        ]

        return Response(
            {
                "ytd": {
                    "bookings": bookings_count,
                    "gross_revenue": f"{gross:.2f}" if gross is not None else None,
                    "net_to_owner": f"{net_to_owner:.2f}" if net_to_owner is not None else None,
                },
                "properties": {"total": len(property_ids), "by_status": by_status},
                "upcoming_arrivals": upcoming_payload,
            }
        )


class OwnerBookingViewSet(viewsets.ReadOnlyModelViewSet):
    """`GET /owner/bookings` (+ `/{id}`) — scoped, redacted booking reads.

    Server-side scoping restricts to the caller's granted properties, so a
    retrieve of any other booking 404s. Field-level redaction lives in the
    serializer, keyed off the per-property visibility map placed in context.
    DRAFT and archived bookings are hidden; cancellations stay visible as
    history.
    """

    permission_classes = [IsOwner]

    def get_serializer_class(self) -> type[serializers.BaseSerializer]:
        if self.action == "retrieve":
            return OwnerBookingDetailSerializer
        return OwnerBookingListSerializer

    def get_queryset(self) -> QuerySet[Booking]:
        user = cast("User", self.request.user)
        property_ids = owner_property_ids(user)
        # "Repeat guest" = this guest has another booking at the caller's own
        # villas — a single correlated EXISTS, constant-query regardless of rows.
        repeat = Exists(
            Booking.objects.filter(
                guest_id=OuterRef("guest_id"), property_id__in=property_ids
            ).exclude(pk=OuterRef("pk"))
        )
        return (
            Booking.objects.filter(property_id__in=property_ids, is_archived=False)
            .exclude(status=BookingStatus.DRAFT.value)
            .select_related("property", "guest", "guest__country", "currency")
            .annotate(is_repeat_guest=repeat)
            .order_by("-date_from")
        )

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        context["visibility"] = owner_visibility_map(cast("User", self.request.user))
        return context
