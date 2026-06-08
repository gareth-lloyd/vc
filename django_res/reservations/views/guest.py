"""`/guests` CRUD plus :merge, :anonymize and nested reads.

All non-trivial state lives on `Guest.merge` / `Guest.anonymize`. The view
only validates the request body and delegates.
"""

from __future__ import annotations

from typing import Any, cast

from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend, FilterSet
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from core.api import IsStaff, IsStaffRoleAdmin
from reservations.models import Booking, Guest, Quotation, QuotationLine
from reservations.serializers import (
    GuestBookingSerializer,
    GuestEnquirySerializer,
    GuestMergeSerializer,
    GuestQuotationSerializer,
    GuestSerializer,
)


def _enquiry_history_prefetch() -> Prefetch:
    """The 3-level quote-stack the history serializer walks (quotations →
    selected lines → live bookings), applied to a guest's enquiry queryset so
    `/guests/{id}/enquiries` stays query-bounded regardless of row count.

    `booking-`-prefixed synthetic quotations (BookingLoader legacy-fill rows)
    are excluded at the source, so the prefetch cache `GuestEnquirySerializer`
    reads is already clean — they must not inflate `quote_count` or
    mis-attribute the converted booking.
    """
    bookings = Booking.objects.only(
        "id", "reference", "status", "is_archived", "created_at", "quotation_line_id"
    )
    lines = QuotationLine.objects.prefetch_related(Prefetch("bookings", queryset=bookings))
    quotations = Quotation.objects.exclude(legacy_id__startswith="booking-").prefetch_related(
        Prefetch("lines", queryset=lines)
    )
    return Prefetch("quotations", queryset=quotations)


class GuestFilterSet(FilterSet):
    class Meta:
        model = Guest
        fields = {
            "status": ["exact"],
            "country": ["exact"],
            "marketing_consent": ["exact"],
        }


class GuestViewSet(viewsets.ModelViewSet[Guest]):
    """`/guests` — CRUD + state-transition actions."""

    queryset = Guest.objects.all()
    serializer_class = GuestSerializer
    permission_classes = [IsStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = GuestFilterSet
    search_fields = ["first_name", "last_name", "email"]
    ordering_fields = ["last_name", "first_name", "created_at"]

    @action(detail=True, methods=["get"], url_path="bookings")
    def bookings(self, request: Request, pk: str | None = None) -> Response:
        guest = self.get_object()
        qs = guest.bookings.all().order_by("-created_at")
        page = self.paginate_queryset(cast(Any, qs))
        ser = GuestBookingSerializer(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    @action(detail=True, methods=["get"], url_path="enquiries")
    def enquiries(self, request: Request, pk: str | None = None) -> Response:
        guest = self.get_object()
        qs = (
            guest.enquiries.all()
            .order_by("-created_at")
            .prefetch_related(_enquiry_history_prefetch())
        )
        page = self.paginate_queryset(cast(Any, qs))
        ser = GuestEnquirySerializer(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)

    @action(detail=True, methods=["get"], url_path="quotations")
    def quotations(self, request: Request, pk: str | None = None) -> Response:
        guest = self.get_object()
        qs = guest.quotations.all().order_by("-created_at")
        page = self.paginate_queryset(cast(Any, qs))
        ser = GuestQuotationSerializer(page or qs, many=True)
        return self.get_paginated_response(ser.data) if page is not None else Response(ser.data)


class GuestMergeView(viewsets.ViewSet):
    """`POST /guests/{id}:merge` — delegates to `Guest.merge(target)`.

    Destructive (hard-deletes the source) so we gate on `IsStaffRoleAdmin`.
    """

    permission_classes = [IsStaffRoleAdmin]

    def create(self, request: Request, pk: str | None = None) -> Response:
        source = get_object_or_404(Guest, pk=pk)
        serializer = GuestMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = get_object_or_404(Guest, pk=serializer.validated_data["target_guest_id"])
        try:
            source.merge(target)
        except ValueError as exc:
            return Response(
                {"code": "merge_invalid", "detail": str(exc), "field_errors": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(GuestSerializer(target).data, status=status.HTTP_200_OK)


class GuestAnonymizeView(viewsets.ViewSet):
    """`POST /guests/{id}:anonymize` — delegates to `Guest.anonymize()`.

    Admin-only — GDPR-class operation. Idempotent (running twice on an
    already-anonymized guest leaves the redacted state intact).
    """

    permission_classes = [IsStaffRoleAdmin]

    def create(self, request: Request, pk: str | None = None) -> Response:
        guest = get_object_or_404(Guest, pk=pk)
        guest.anonymize()
        return Response(GuestSerializer(guest).data, status=status.HTTP_200_OK)
