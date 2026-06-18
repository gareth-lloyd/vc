"""Cross-booking concierge coverage matrix endpoints.

- ``GET  /concierge/overview`` — every live booking as a matrix row.
- ``POST /concierge/{booking_id}/coverage/{service}:set-status`` — upsert one
  service cell's progress status.

Live = not archived, not in a terminal state, and not already departed
(``date_to >= today``); rows are ordered by arrival so the soonest stays sit
at the top of the matrix.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import status as http_status
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsReservationsWriter
from reservations.enums import (
    TERMINAL_BOOKING_STATUSES,
    ConciergeService,
    ServiceStatus,
)
from reservations.models import Booking
from reservations.serializers.concierge_overview import (
    BookingServiceCoverageSerializer,
    ConciergeOverviewSerializer,
)
from reservations.services.service_coverage import ConciergeCoverageService


class ConciergeOverviewViewSet(viewsets.ViewSet):
    """Read the matrix; write a single coverage cell."""

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def _live_bookings(self, today: date) -> Any:
        return (
            Booking.objects.filter(is_archived=False)
            .exclude(status__in=TERMINAL_BOOKING_STATUSES)
            .filter(date_to__gte=today)
            .select_related("property__region", "person", "assigned_to")
            .prefetch_related("service_coverage", "concierge_items")
            .order_by("date_from")
        )

    def list(self, request: Request) -> Response:
        today = date.today()
        serializer = ConciergeOverviewSerializer(
            self._live_bookings(today),
            many=True,
            context={"today": today},
        )
        return Response(serializer.data)

    def set_status(self, request: Request, booking_id: int, service: str) -> Response:
        new_status = request.data.get("status")
        if service not in ConciergeService.values:
            return self._bad_request(f"Unknown service '{service}'")
        if new_status not in ServiceStatus.values:
            return self._bad_request(f"Unknown status '{new_status}'")
        # Write scope must match read scope: only live bookings are writable.
        booking = get_object_or_404(self._live_bookings(date.today()), pk=booking_id)
        coverage = ConciergeCoverageService.set_status(
            booking=booking,
            service=service,
            status=new_status,
            actor=request.user,
        )
        return Response(BookingServiceCoverageSerializer(coverage).data)

    @staticmethod
    def _bad_request(detail: str) -> Response:
        return Response(
            {"code": "validation_error", "detail": detail, "field_errors": {}},
            status=http_status.HTTP_400_BAD_REQUEST,
        )
