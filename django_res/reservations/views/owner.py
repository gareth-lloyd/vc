"""Owner-portal booking-backed endpoints.

These live in `reservations` (not `owners`) because they read
`reservations.Booking`: the import spine runs reservations → owners, so a
reservations view may import `owners.scoping` / `owners.permissions` downward,
but `owners` may not reach up to Booking. Property/identity-only owner views
stay in the `owners` app.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, cast

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from owners.permissions import IsOwner
from owners.scoping import owner_property_ids, owner_visibility_map
from properties.models import Property
from reservations.enums import BookingStatus
from reservations.models import Booking

if TYPE_CHECKING:
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


def _net_from_snapshot(snapshot: dict[str, Any]) -> Decimal | None:
    """Owner-net from a pricing snapshot — mirrors BookingDetailSerializer.

    Prefers the explicit `net_to_owner` the engine writes; falls back to
    `total - commission - tax` for legacy/older snapshots. Returns None when
    the snapshot lacks the figures (e.g. `{}` on imported rows).
    """
    try:
        total = Decimal(str(snapshot["total"]))
        commission = Decimal(str(snapshot["commission"]))
        tax = Decimal(str(snapshot["tax"]))
    except (KeyError, InvalidOperation, TypeError):
        return None
    raw_net = snapshot.get("net_to_owner")
    if raw_net is not None:
        try:
            return Decimal(str(raw_net))
        except (InvalidOperation, TypeError):
            pass
    return total - commission - tax


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
        agg = ytd.aggregate(bookings=Count("id"), gross=Sum("rental_price"))
        gross = agg["gross"] or Decimal("0")

        full_money_ids = {pid for pid, flags in visibility.items() if flags["view_full_money"]}
        net_to_owner: Decimal | None = None
        if full_money_ids:
            net_to_owner = Decimal("0")
            for snapshot in ytd.filter(property_id__in=full_money_ids).values_list(
                "pricing_snapshot", flat=True
            ):
                net = _net_from_snapshot(snapshot or {})
                if net is not None:
                    net_to_owner += net

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
                    "bookings": agg["bookings"],
                    "gross_revenue": f"{gross:.2f}",
                    "net_to_owner": f"{net_to_owner:.2f}" if net_to_owner is not None else None,
                },
                "properties": {"total": len(property_ids), "by_status": by_status},
                "upcoming_arrivals": upcoming_payload,
            }
        )
