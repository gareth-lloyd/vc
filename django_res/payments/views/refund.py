"""Refund viewset — list/create/detail + state action endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsAccountsWriter
from core.exceptions import InvalidPaymentState
from payments.filters import RefundFilter
from payments.models import Payment, Refund
from payments.serializers import RefundRequestSerializer, RefundSerializer
from payments.services.refund import RefundService
from reservations.models import Booking


class RefundViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """`/refunds` — list + detail. Creation lives under `/bookings/{id}/refunds`."""

    serializer_class = RefundSerializer
    permission_classes = [IsAuthenticated, IsAccountsWriter]
    filterset_class = RefundFilter
    ordering_fields = ["created_at", "requested_at", "amount", "status"]
    ordering = ["-created_at"]

    def get_queryset(self) -> Any:
        return Refund.objects.select_related(
            "booking",
            "currency",
            "against_payment",
            "requested_by",
            "approved_by",
            "rejected_by",
            "executed_by",
            "security_deposit",
        )

    # ------------------------------------------------------------------
    # Action endpoints
    # ------------------------------------------------------------------
    # Service-layer rejections surface through the canonical exception handler:
    # `AuthorizationError` → 403 `forbidden`, `InvalidPaymentState` → 409
    # `invalid_state`. No per-action `except` re-mapping (SMELL-010).
    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request: Request, pk: str | None = None) -> Response:
        refund = self.get_object()
        RefundService.approve(refund, actor=request.user)
        refund.refresh_from_db()
        return Response(RefundSerializer(refund).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request: Request, pk: str | None = None) -> Response:
        refund = self.get_object()
        reason = request.data.get("reason", "")
        RefundService.reject(refund, actor=request.user, reason=reason)
        refund.refresh_from_db()
        return Response(RefundSerializer(refund).data)

    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request: Request, pk: str | None = None) -> Response:
        refund = self.get_object()
        # Optional single field; mirror the sibling `reject` action's inline
        # read rather than adding a serializer. TfaStepUpRequired (403) /
        # InvalidTfaCode (400) surface through the canonical handler.
        RefundService.execute(refund, actor=request.user, tfa_code=request.data.get("tfa_code"))
        refund.refresh_from_db()
        return Response(RefundSerializer(refund).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        refund = self.get_object()
        RefundService.cancel(refund, actor=request.user)
        refund.refresh_from_db()
        return Response(RefundSerializer(refund).data)


def request_refund_for_booking(request: Request, booking_pk: int) -> Response:
    """`POST /bookings/{id}/refunds` — open a new refund against the booking."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    serializer = RefundRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    against_payment_id = data.get("against_payment")
    against_payment: Payment | None = None
    if against_payment_id is not None:
        against_payment = get_object_or_404(
            Payment,
            pk=against_payment_id,
            booking=booking,
        )
    currency = data.get("currency") or booking.currency
    try:
        refund = RefundService.request(
            booking=booking,
            amount=Decimal(str(data["amount"])),
            currency=currency,
            purpose_track=data["purpose_track"],
            reason_code=data["reason_code"],
            reason_notes=data.get("reason_notes", ""),
            method=data.get("method", "online_gateway"),
            against_payment=against_payment,
            requested_by=request.user,
            idempotency_key=data["idempotency_key"] or None,
        )
    except IntegrityError as exc:
        # FG-010: two racing requests with the same key both pass the
        # service's `find_by_meta_key` pre-check under READ COMMITTED; the
        # loser hits `refund_idempotency_key_unique_per_booking`. That's a
        # conflict, not a 500 — mirrors `_service_call` in views/track.py.
        raise InvalidPaymentState("A conflicting refund already exists for this booking.") from exc
    return Response(RefundSerializer(refund).data, status=status.HTTP_201_CREATED)


def list_refunds_for_booking(request: Request, booking_pk: int) -> Response:
    """`GET /bookings/{id}/refunds` — scoped list."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    refunds = Refund.objects.filter(booking=booking).order_by("-created_at")
    return Response(RefundSerializer(refunds, many=True).data)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def refunds_for_booking(request: Request, booking_pk: int) -> Response:
    """Dispatcher for `/bookings/{id}/refunds` (GET list, POST create)."""
    if request.method == "GET":
        return list_refunds_for_booking(request, booking_pk)
    return request_refund_for_booking(request, booking_pk)
