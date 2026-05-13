"""Refund viewset — list/create/detail + state action endpoints."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsAccountsWriter
from payments.filters import RefundFilter
from payments.models import Payment, Refund
from payments.serializers import RefundRequestSerializer, RefundSerializer
from payments.services.refund import RefundService
from reservations.models import Booking


def _run_service(call: Callable[[], Any]) -> Response | None:
    """Translate service-layer `PermissionError`s into a canonical 403.

    `ValueError` (state-machine misuse) maps to 409 so the FE can branch on
    "wrong status" vs "auth missing" cleanly. Returns `None` on success.
    """
    try:
        call()
    except PermissionError as exc:
        return Response(
            {
                "code": "forbidden",
                "detail": str(exc) or "Permission denied",
                "field_errors": {},
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    except ValueError as exc:
        return Response(
            {"code": "invalid_state", "detail": str(exc), "field_errors": {}},
            status=status.HTTP_409_CONFLICT,
        )
    return None


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
    @action(detail=True, methods=["post"], url_path="approve")
    def approve(self, request: Request, pk: str | None = None) -> Response:
        refund = self.get_object()
        error = _run_service(lambda: RefundService.approve(refund, actor=request.user))
        if error is not None:
            return error
        refund.refresh_from_db()
        return Response(RefundSerializer(refund).data)

    @action(detail=True, methods=["post"], url_path="reject")
    def reject(self, request: Request, pk: str | None = None) -> Response:
        refund = self.get_object()
        reason = request.data.get("reason", "")
        error = _run_service(
            lambda: RefundService.reject(refund, actor=request.user, reason=reason)
        )
        if error is not None:
            return error
        refund.refresh_from_db()
        return Response(RefundSerializer(refund).data)

    @action(detail=True, methods=["post"], url_path="execute")
    def execute(self, request: Request, pk: str | None = None) -> Response:
        refund = self.get_object()
        error = _run_service(lambda: RefundService.execute(refund, actor=request.user))
        if error is not None:
            return error
        refund.refresh_from_db()
        return Response(RefundSerializer(refund).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        refund = self.get_object()
        error = _run_service(lambda: RefundService.cancel(refund, actor=request.user))
        if error is not None:
            return error
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
    )
    return Response(RefundSerializer(refund).data, status=status.HTTP_201_CREATED)


def list_refunds_for_booking(request: Request, booking_pk: int) -> Response:
    """`GET /bookings/{id}/refunds` — scoped list."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    refunds = Refund.objects.filter(booking=booking).order_by("-created_at")
    return Response(RefundSerializer(refunds, many=True).data)
