"""Viewset for nested damage claims (`/bookings/{id}/damage-claims`)."""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsReservationsWriter
from reservations.models import Booking, DamageClaim
from reservations.serializers import DamageClaimSerializer, DamageClaimWriteSerializer
from reservations.services.damage_claims import DamageClaimService


class DamageClaimViewSet(viewsets.ModelViewSet):
    """`/bookings/{id}/damage-claims` CRUD + `:withdraw`.

    Filing/editing a claim is reservations-side operator work (RESERVATIONS
    role); the money move it justifies stays separately accounts-gated on the
    SD `:claim` endpoint. All writes route through `DamageClaimService` — it
    owns the currency pin, the positive-amount guard, and the actor stamp.
    """

    permission_classes = [IsAuthenticated, IsReservationsWriter]

    def get_queryset(self) -> Any:
        return (
            DamageClaim.objects.filter(booking_id=self.kwargs["booking_pk"])
            .select_related("booking", "currency")
            .prefetch_related("photos")
            .order_by("-created_at")
        )

    def get_serializer_class(self) -> type:
        if self.action in ("create", "update", "partial_update"):
            return DamageClaimWriteSerializer
        return DamageClaimSerializer

    # Writes accept the write serializer but respond with the read
    # representation (reference, currency_code, status, timestamps) so the FE
    # can use the result without a follow-up fetch.
    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            DamageClaimSerializer(serializer.instance).data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(DamageClaimSerializer(serializer.instance).data)

    def perform_create(self, serializer: Any) -> None:
        booking = get_object_or_404(Booking, pk=self.kwargs["booking_pk"])
        serializer.instance = DamageClaimService.create(
            booking,
            actor=self.request.user,
            **serializer.validated_data,
        )

    def perform_update(self, serializer: Any) -> None:
        serializer.instance = DamageClaimService.update(
            serializer.instance,
            actor=self.request.user,
            **serializer.validated_data,
        )

    def perform_destroy(self, instance: Any) -> None:
        DamageClaimService.delete(instance, actor=self.request.user)

    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        claim = DamageClaimService.approve(self.get_object(), actor=request.user)
        return Response(DamageClaimSerializer(claim).data)

    @action(detail=True, methods=["post"], url_path="withdraw")
    def withdraw(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        claim = DamageClaimService.withdraw(self.get_object(), actor=request.user)
        return Response(DamageClaimSerializer(claim).data)
