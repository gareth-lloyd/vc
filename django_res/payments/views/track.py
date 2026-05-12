"""Track endpoints — deposit, balance, security.

Each track is a synthesized view across `Payment` rows for the booking
sharing a single `purpose`. The functional views below compose the
serializer + service-layer transitions; the booking-side track endpoints
delegate to `SecurityDepositService` / `Payment` model methods.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsAccountsWriter
from core.api.responses import not_implemented_response
from payments.enums import (
    PaymentMethod,
    PaymentPurpose,
    PaymentStatus,
    SecurityDepositStatus,
)
from payments.models import Payment, SecurityDeposit
from payments.serializers import PaymentSerializer, TrackSerializer
from payments.services.security_deposit import SecurityDepositService
from reservations.models import Booking


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _track_response(booking: Booking, purpose: str) -> Response:
    data = TrackSerializer.for_booking_purpose(booking=booking, purpose=purpose)
    return Response(data)


def _ensure_authenticated_writer(request: Request) -> Response | None:
    """Lightweight gate for the function-based views (DRF's class-based
    permissions don't fire on `@api_view` without `permission_classes`).
    """
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
    return None


def _parse_decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# ----------------------------------------------------------------------
# DEPOSIT track
# ----------------------------------------------------------------------
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def deposit_track(request: Request, booking_pk: int) -> Response:
    """`/bookings/{id}/deposit` — GET reads the synthesized track view; PATCH
    updates the scheduled `Payment(purpose=DEPOSIT)` row's amount / due_at.
    """
    booking = get_object_or_404(Booking, pk=booking_pk)
    if request.method == "PATCH":
        row = (
            Payment.objects.filter(
                booking=booking,
                purpose=PaymentPurpose.DEPOSIT.value,
                status=PaymentStatus.PENDING.value,
            )
            .order_by("-created_at")
            .first()
        )
        if row is None:
            return Response(
                {
                    "code": "no_pending_payment",
                    "detail": "No pending deposit payment to update",
                    "field_errors": {},
                },
                status=status.HTTP_409_CONFLICT,
            )
        updates: list[str] = []
        if "amount" in request.data:
            row.amount = _parse_decimal(request.data["amount"])
            updates.append("amount")
        if "due_at" in request.data and request.data["due_at"] is not None:
            row.due_at = _parse_datetime(request.data["due_at"])
            updates.append("due_at")
        if updates:
            updates.append("updated_at")
            row.save(update_fields=updates)
    return _track_response(booking, PaymentPurpose.DEPOSIT.value)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def deposit_payments(request: Request, booking_pk: int) -> Response:
    """`/bookings/{id}/deposit/payments` — list or record a manual payment."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    return _track_payments(request, booking, PaymentPurpose.DEPOSIT.value)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def deposit_track_action(request: Request, booking_pk: int, action: str) -> Response:
    """`/bookings/{id}/deposit:<action>` — request-payment / mark-paid / waive."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    return _track_action(request, booking, PaymentPurpose.DEPOSIT.value, action)


# ----------------------------------------------------------------------
# BALANCE track — mirrors deposit
# ----------------------------------------------------------------------
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def balance_track(request: Request, booking_pk: int) -> Response:
    booking = get_object_or_404(Booking, pk=booking_pk)
    if request.method == "PATCH":
        row = (
            Payment.objects.filter(
                booking=booking,
                purpose=PaymentPurpose.BALANCE.value,
                status=PaymentStatus.PENDING.value,
            )
            .order_by("-created_at")
            .first()
        )
        if row is None:
            return Response(
                {
                    "code": "no_pending_payment",
                    "detail": "No pending balance payment to update",
                    "field_errors": {},
                },
                status=status.HTTP_409_CONFLICT,
            )
        updates: list[str] = []
        if "amount" in request.data:
            row.amount = _parse_decimal(request.data["amount"])
            updates.append("amount")
        if "due_at" in request.data and request.data["due_at"] is not None:
            row.due_at = _parse_datetime(request.data["due_at"])
            updates.append("due_at")
        if updates:
            updates.append("updated_at")
            row.save(update_fields=updates)
    return _track_response(booking, PaymentPurpose.BALANCE.value)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def balance_payments(request: Request, booking_pk: int) -> Response:
    booking = get_object_or_404(Booking, pk=booking_pk)
    return _track_payments(request, booking, PaymentPurpose.BALANCE.value)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def balance_track_action(request: Request, booking_pk: int, action: str) -> Response:
    booking = get_object_or_404(Booking, pk=booking_pk)
    return _track_action(request, booking, PaymentPurpose.BALANCE.value, action)


# ----------------------------------------------------------------------
# SECURITY track (delegates to SecurityDepositService where needed)
# ----------------------------------------------------------------------
@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def security_track(request: Request, booking_pk: int) -> Response:
    booking = get_object_or_404(Booking, pk=booking_pk)
    return _track_response(booking, PaymentPurpose.SECURITY_DEPOSIT.value)


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def security_payments(request: Request, booking_pk: int) -> Response:
    booking = get_object_or_404(Booking, pk=booking_pk)
    return _track_payments(request, booking, PaymentPurpose.SECURITY_DEPOSIT.value)


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def security_track_action(request: Request, booking_pk: int, action: str) -> Response:
    booking = get_object_or_404(Booking, pk=booking_pk)
    if action == "request-payment":
        return not_implemented_response("Security request-payment is not yet implemented.")
    if action == "mark-paid":
        sd = _get_active_sd(booking)
        SecurityDepositService.mark_paid(
            sd,
            amount=_parse_decimal(request.data["amount"]),
            paid_at=_parse_datetime(request.data["paid_at"]),
            method=request.data.get("method", PaymentMethod.BANK_TRANSFER.value),
            reference=request.data.get("reference", ""),
            actor=request.user,
        )
        sd.refresh_from_db()
        return _track_response(booking, PaymentPurpose.SECURITY_DEPOSIT.value)
    return Response(
        {"code": "unknown_action", "detail": f"Unknown action {action!r}", "field_errors": {}},
        status=status.HTTP_400_BAD_REQUEST,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def security_payment_action(
    request: Request, booking_pk: int, payment_pk: int, action: str
) -> Response:
    """Per-payment SD actions: capture / hold / release / claim."""
    booking = get_object_or_404(Booking, pk=booking_pk)
    if action == "capture":
        return _payment_capture(request, booking, payment_pk)
    sd = _get_active_sd(booking)
    if action == "hold":
        SecurityDepositService.hold(
            sd,
            gateway_response=request.data.get("gateway_response", {}),
            actor=request.user,
        )
    elif action == "release":
        SecurityDepositService.release(sd, actor=request.user)
    elif action == "claim":
        SecurityDepositService.claim(
            sd,
            damage_claim=request.data.get("damage_claim"),
            captured_amount=_parse_decimal(request.data.get("captured_amount", sd.amount)),
            actor=request.user,
        )
    else:
        return Response(
            {"code": "unknown_action", "detail": f"Unknown action {action!r}", "field_errors": {}},
            status=status.HTTP_400_BAD_REQUEST,
        )
    sd.refresh_from_db()
    return _track_response(booking, PaymentPurpose.SECURITY_DEPOSIT.value)


def _get_active_sd(booking: Booking) -> SecurityDeposit:
    sd = (
        SecurityDeposit.objects.filter(booking=booking)
        .exclude(
            status__in=(
                SecurityDepositStatus.RELEASED.value,
                SecurityDepositStatus.REFUNDED.value,
                SecurityDepositStatus.EXPIRED.value,
                SecurityDepositStatus.FAILED.value,
            )
        )
        .order_by("-created_at")
        .first()
    )
    if sd is None:
        raise _ConflictError("No active SecurityDeposit for this booking", code="no_active_sd")
    return sd


class _ConflictError(Exception):
    def __init__(self, detail: str, *, code: str) -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code


# ----------------------------------------------------------------------
# Per-payment actions (deposit / balance): capture / void
# ----------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def payment_action(
    request: Request, booking_pk: int, purpose: str, payment_pk: int, action: str
) -> Response:
    booking = get_object_or_404(Booking, pk=booking_pk)
    if action == "capture":
        return _payment_capture(request, booking, payment_pk)
    if action == "void":
        return _payment_void(request, booking, payment_pk)
    return Response(
        {"code": "unknown_action", "detail": f"Unknown action {action!r}", "field_errors": {}},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _payment_capture(request: Request, booking: Booking, payment_pk: int) -> Response:
    payment = get_object_or_404(Payment, pk=payment_pk, booking=booking)
    if payment.status != PaymentStatus.PROCESSING.value:
        return Response(
            {
                "code": "invalid_state",
                "detail": f"Cannot capture from status {payment.status!r}",
                "field_errors": {},
            },
            status=status.HTTP_409_CONFLICT,
        )
    payment.transition_to(PaymentStatus.SUCCEEDED.value, actor=request.user, kind="CAPTURE")
    payment.refresh_from_db()
    return Response(PaymentSerializer(payment).data)


def _payment_void(request: Request, booking: Booking, payment_pk: int) -> Response:
    payment = get_object_or_404(Payment, pk=payment_pk, booking=booking)
    if payment.status not in (
        PaymentStatus.PENDING.value,
        PaymentStatus.PROCESSING.value,
    ):
        return Response(
            {
                "code": "invalid_state",
                "detail": f"Cannot void from status {payment.status!r}",
                "field_errors": {},
            },
            status=status.HTTP_409_CONFLICT,
        )
    payment.transition_to(PaymentStatus.CANCELLED.value, actor=request.user, kind="VOID")
    payment.refresh_from_db()
    return Response(PaymentSerializer(payment).data)


# ----------------------------------------------------------------------
# Shared list/create + action helpers
# ----------------------------------------------------------------------
def _track_payments(request: Request, booking: Booking, purpose: str) -> Response:
    if request.method == "GET":
        rows = Payment.objects.filter(booking=booking, purpose=purpose).order_by("-created_at")
        return Response(PaymentSerializer(rows, many=True).data)
    # POST — record a manual payment
    data = request.data
    payment = Payment.objects.create(
        booking=booking,
        purpose=purpose,
        status=data.get("status", PaymentStatus.PENDING.value),
        amount=_parse_decimal(data.get("amount", 0)),
        currency=booking.currency,
        provider=data.get("provider", ""),
        provider_reference=data.get("provider_reference", ""),
        payment_method=data.get("payment_method", ""),
        due_at=_parse_datetime(data["due_at"]) if data.get("due_at") else None,
        meta=data.get("meta", {}),
    )
    return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


def _track_action(request: Request, booking: Booking, purpose: str, action: str) -> Response:
    if action == "request-payment":
        return not_implemented_response("request-payment is not yet implemented.")
    pending = (
        Payment.objects.filter(
            booking=booking,
            purpose=purpose,
            status=PaymentStatus.PENDING.value,
        )
        .order_by("-created_at")
        .first()
    )
    if pending is None:
        return Response(
            {
                "code": "no_pending_payment",
                "detail": "No pending payment to action",
                "field_errors": {},
            },
            status=status.HTTP_409_CONFLICT,
        )
    if action == "mark-paid":
        amount = _parse_decimal(request.data.get("amount", pending.amount))
        paid_at = _parse_datetime(request.data.get("paid_at", timezone.now().isoformat()))
        method = request.data.get("method", PaymentMethod.BANK_TRANSFER.value)
        reference = request.data.get("reference", "")
        pending.mark_paid(
            amount=amount,
            paid_at=paid_at,
            method=method,
            reference=reference,
            notes=request.data.get("notes", ""),
            actor=request.user,
        )
        pending.refresh_from_db()
        return _track_response(booking, purpose)
    if action == "waive":
        pending.waive(reason=request.data.get("reason", ""), actor=request.user)
        pending.refresh_from_db()
        return _track_response(booking, purpose)
    return Response(
        {"code": "unknown_action", "detail": f"Unknown action {action!r}", "field_errors": {}},
        status=status.HTTP_400_BAD_REQUEST,
    )
