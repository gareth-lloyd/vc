"""Viewset for nested damage claims (`/bookings/{id}/damage-claims`)."""

from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsReservationsWriter
from reservations.models import Booking, DamageClaim, DamageClaimPhoto
from reservations.serializers import (
    DamageClaimPhotoSerializer,
    DamageClaimPhotoWriteSerializer,
    DamageClaimSerializer,
    DamageClaimWriteSerializer,
)
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


def _scoped_photos(booking_pk: int, claim_pk: int) -> Any:
    """Photos for one claim, double-scoped by booking + claim (IDOR guard).

    A photo is only reachable through the URL of the booking that owns its
    claim — a cross-booking `{booking}/{claim}/photos/{id}` 404s rather than
    leaking or destroying another booking's evidence.
    """
    return DamageClaimPhoto.objects.filter(
        damage_claim_id=claim_pk,
        damage_claim__booking_id=booking_pk,
    )


class DamageClaimPhotoListCreateView(generics.ListAPIView):
    """`GET` lists a claim's photos; `POST` uploads one (multipart)."""

    serializer_class = DamageClaimPhotoSerializer
    permission_classes = [IsAuthenticated, IsReservationsWriter]
    # The default parser set is JSON-only; the upload arrives as multipart.
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self) -> Any:
        return _scoped_photos(self.kwargs["booking_pk"], self.kwargs["claim_pk"])

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # Resolve the claim through the booking scope so a photo can't be
        # attached to another booking's claim.
        claim = get_object_or_404(
            DamageClaim,
            pk=self.kwargs["claim_pk"],
            booking_id=self.kwargs["booking_pk"],
        )
        write = DamageClaimPhotoWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        data = write.validated_data
        photo = DamageClaimPhoto.objects.create(
            damage_claim=claim,
            image=data["image"],
            caption=data.get("caption", ""),
        )
        return Response(
            DamageClaimPhotoSerializer(photo).data,
            status=status.HTTP_201_CREATED,
        )


class DamageClaimPhotoDetailView(generics.RetrieveDestroyAPIView):
    """`GET`/`DELETE` a single photo, double-scoped by booking + claim."""

    serializer_class = DamageClaimPhotoSerializer
    permission_classes = [IsAuthenticated, IsReservationsWriter]
    lookup_url_kwarg = "photo_id"

    def get_queryset(self) -> Any:
        return _scoped_photos(self.kwargs["booking_pk"], self.kwargs["claim_pk"])
