"""Viewset for nested manual charge items."""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsReservationsWriter
from reservations.models import Booking, BookingChargeItem
from reservations.serializers import (
    BookingChargeItemSerializer,
    BookingChargeItemWriteSerializer,
)
from reservations.services.charges import ChargeItemService


class BookingChargeItemViewSet(viewsets.ModelViewSet):
    """`/bookings/{id}/charge-items` CRUD.

    All writes route through `ChargeItemService` — it owns the booking
    row lock, the active-state gate, the currency pin, the negative-total
    guard and the BookingEvent trail.
    """

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> Any:
        return (
            BookingChargeItem.objects.filter(booking_id=self.kwargs["booking_pk"])
            .select_related("currency")
            .order_by("pk")
        )

    def get_serializer_class(self) -> type:
        if self.action in ("create", "update", "partial_update"):
            return BookingChargeItemWriteSerializer
        return BookingChargeItemSerializer

    # Writes accept the write serializer but respond with the read
    # representation (id, currency_code, timestamps) so the FE can parse
    # the result without a follow-up fetch.
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            BookingChargeItemSerializer(serializer.instance).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(BookingChargeItemSerializer(serializer.instance).data)

    def perform_create(self, serializer: Any) -> None:
        booking = get_object_or_404(Booking, pk=self.kwargs["booking_pk"])
        serializer.instance = ChargeItemService.create(
            booking,
            actor=self.request.user,
            **serializer.validated_data,
        )

    def perform_update(self, serializer: Any) -> None:
        serializer.instance = ChargeItemService.update(
            serializer.instance,
            actor=self.request.user,
            **serializer.validated_data,
        )

    def perform_destroy(self, instance: Any) -> None:
        ChargeItemService.delete(instance, actor=self.request.user)
