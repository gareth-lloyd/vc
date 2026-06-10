"""Viewsets for nested concierge items."""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsReservationsWriter
from reservations.enums import ConciergeStatus
from reservations.models import Booking, BookingConciergeItem
from reservations.serializers import (
    BookingConciergeItemSerializer,
    BookingConciergeItemWriteSerializer,
)


class BookingConciergeItemViewSet(viewsets.ModelViewSet):
    """`/bookings/{id}/concierge-items` CRUD + :reorder + per-item :confirm."""

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> Any:
        return BookingConciergeItem.objects.filter(
            booking_id=self.kwargs["booking_pk"],
        ).order_by("pk")

    def get_serializer_class(self) -> type:
        if self.action in ("create", "update", "partial_update"):
            return BookingConciergeItemWriteSerializer
        return BookingConciergeItemSerializer

    # Writes accept the write serializer but respond with the read
    # representation (id, status, timestamps) so the FE can parse the
    # result without a follow-up fetch.
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            BookingConciergeItemSerializer(serializer.instance).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(BookingConciergeItemSerializer(serializer.instance).data)

    def perform_create(self, serializer: Any) -> None:
        booking = get_object_or_404(Booking, pk=self.kwargs["booking_pk"])
        serializer.save(booking=booking)

    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder(self, request: Request, booking_pk: str | None = None) -> Response:
        """Reorder by id list. No `sort_order` column — confirms membership only."""
        ids = request.data.get("ids", [])
        if not isinstance(ids, list):
            return Response(
                {"code": "validation_error", "detail": "`ids` must be a list", "field_errors": {}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        items = list(self.get_queryset().filter(pk__in=ids))
        return Response(BookingConciergeItemSerializer(items, many=True).data)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(
        self, request: Request, booking_pk: str | None = None, pk: str | None = None
    ) -> Response:
        """Mark an item CONFIRMED."""
        item = self.get_object()
        item.status = ConciergeStatus.CONFIRMED.value
        item.save(update_fields=["status", "updated_at"])
        return Response(BookingConciergeItemSerializer(item).data)
