"""Viewset for nested manual charge items."""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

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
