"""Track endpoints — deposit, balance, security.

Each track is a synthesized view across `Payment` rows for the booking
sharing a single `purpose`. The functional views below compose the
serializer + service-layer transitions; the booking-side track endpoints
delegate to `SecurityDepositService` / `Payment` model methods.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from core.api.permissions import IsAccountsWriter
from core.api.responses import not_implemented_response
from core.exceptions import (
    InvalidPaymentState,
    NoActiveSecurityDeposit,
    NoPendingPayment,
    UnknownAction,
)
from payments.enums import (
    TERMINAL_SD_STATUSES,
    PaymentMethod,
    PaymentPurpose,
    PaymentStatus,
)
from payments.models import Payment, SecurityDeposit
from payments.serializers import (
    ManualPaymentCreateSerializer,
    PaymentSerializer,
    TrackSerializer,
)
from payments.services.manual_payment import ManualPaymentService
from payments.services.security_deposit import SecurityDepositService
from reservations.models import Booking


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _track_response(booking: Booking, purpose: str) -> Response:
    data = TrackSerializer.for_booking_purpose(booking=booking, purpose=purpose)
    # Route through the serializer so DecimalField renders amounts as
    # strings (the FE Zod schema expects strings); bypassing it would send
    # raw Decimals straight to the JSON renderer as numbers.
    return Response(TrackSerializer(data).data)


def _parse_decimal(value: Any, *, field: str = "amount") -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise DRFValidationError({field: ["A valid decimal number is required."]}) from None


def _parse_positive_decimal(value: Any, *, field: str = "amount") -> Decimal:
    amount = _parse_decimal(value, field=field)
    if amount <= 0:
        raise DRFValidationError({field: ["Must be greater than zero."]})
    return amount


def _parse_datetime(value: Any, *, field: str = "due_at") -> datetime:
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise DRFValidationError({field: ["A valid ISO-8601 datetime is required."]}) from None


def _service_call[T](call: Callable[[], T]) -> T:
    """Translate service-layer `ValueError`s (state-machine misuse) to 409.

    Mirrors `RefundViewSet._run_service`: the SD/payment *status* guards still
    raise `ValueError` (SMELL-010), which would otherwise surface as a 500.
    Typed `DomainError`s (e.g. `InvalidSecurityDepositKind`, BUG-011) pass
    through untouched — the canonical exception handler maps them itself.
    IntegrityError is the concurrent twin — two racing requests both pass the
    in-memory guards and the loser hits a one-active-row constraint; that's a
    conflict, not a 500.
    """
    try:
        return call()
    except ValueError as exc:
        raise InvalidPaymentState(str(exc)) from exc
    except IntegrityError as exc:
        raise InvalidPaymentState(
            "A conflicting payment row already exists for this booking."
        ) from exc


def _patch_pending_payment(request: Request, booking: Booking, purpose: str) -> None:
    """Common PATCH body for the deposit and balance tracks.

    Raises NoPendingPayment if the scheduled row isn't present in PENDING.
    """
    row = (
        Payment.objects.filter(booking=booking, purpose=purpose, status=PaymentStatus.PENDING.value)
        .order_by("-created_at")
        .first()
    )
    if row is None:
        raise NoPendingPayment(f"No pending {purpose} payment to update")
    updates: list[str] = []
    if "amount" in request.data:
        amount = _parse_decimal(request.data["amount"])
        # Zero is legitimate (a 100%-deposit schedule leaves a zero balance
        # row); negative would invert the ledger.
        if amount < 0:
            raise DRFValidationError({"amount": ["Must not be negative."]})
        row.amount = amount
        updates.append("amount")
    if "due_at" in request.data and request.data["due_at"] is not None:
        row.due_at = _parse_datetime(request.data["due_at"])
        updates.append("due_at")
    if updates:
        updates.append("updated_at")
        row.save(update_fields=updates)


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
        _patch_pending_payment(request, booking, PaymentPurpose.DEPOSIT.value)
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
        _patch_pending_payment(request, booking, PaymentPurpose.BALANCE.value)
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
        if "amount" not in request.data or "paid_at" not in request.data:
            raise DRFValidationError(
                {
                    field: ["This field is required."]
                    for field in ("amount", "paid_at")
                    if field not in request.data
                }
            )
        sd = _get_active_sd(booking)
        _service_call(
            lambda: SecurityDepositService.mark_paid(
                sd,
                amount=_parse_positive_decimal(request.data["amount"]),
                paid_at=_parse_datetime(request.data["paid_at"], field="paid_at"),
                method=request.data.get("method", PaymentMethod.BANK_TRANSFER.value),
                reference=request.data.get("reference", ""),
                actor=request.user,
            )
        )
        return _track_response(booking, PaymentPurpose.SECURITY_DEPOSIT.value)
    raise UnknownAction(f"Unknown action {action!r}")


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
        _service_call(
            lambda: SecurityDepositService.hold(
                sd,
                gateway_response=request.data.get("gateway_response", {}),
                actor=request.user,
            )
        )
    elif action == "release":
        _service_call(lambda: SecurityDepositService.release(sd, actor=request.user))
    elif action == "claim":
        captured = _parse_decimal(
            request.data.get("captured_amount", sd.amount), field="captured_amount"
        )
        _service_call(
            lambda: SecurityDepositService.claim(
                sd,
                damage_claim=request.data.get("damage_claim"),
                captured_amount=captured,
                actor=request.user,
            )
        )
    else:
        raise UnknownAction(f"Unknown action {action!r}")
    return _track_response(booking, PaymentPurpose.SECURITY_DEPOSIT.value)


def _get_active_sd(booking: Booking) -> SecurityDeposit:
    # All terminal statuses are excluded — a CAPTURED or PARTIALLY_REFUNDED
    # deposit is just as closed as a RELEASED one and must not be served as
    # the actionable SD.
    sd = (
        SecurityDeposit.objects.filter(booking=booking)
        .exclude(status__in=TERMINAL_SD_STATUSES)
        .order_by("-created_at")
        .first()
    )
    if sd is None:
        raise NoActiveSecurityDeposit("No active SecurityDeposit for this booking")
    return sd


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
    raise UnknownAction(f"Unknown action {action!r}")


def _payment_capture(request: Request, booking: Booking, payment_pk: int) -> Response:
    payment = get_object_or_404(Payment, pk=payment_pk, booking=booking)
    if payment.status != PaymentStatus.PROCESSING.value:
        raise InvalidPaymentState(f"Cannot capture from status {payment.status!r}")
    payment.transition_to(PaymentStatus.SUCCEEDED.value, actor=request.user, kind="CAPTURE")
    return Response(PaymentSerializer(payment).data)


def _payment_void(request: Request, booking: Booking, payment_pk: int) -> Response:
    payment = get_object_or_404(Payment, pk=payment_pk, booking=booking)
    if payment.status not in (
        PaymentStatus.PENDING.value,
        PaymentStatus.PROCESSING.value,
    ):
        raise InvalidPaymentState(f"Cannot void from status {payment.status!r}")
    payment.transition_to(PaymentStatus.CANCELLED.value, actor=request.user, kind="VOID")
    return Response(PaymentSerializer(payment).data)


# ----------------------------------------------------------------------
# Shared list/create + action helpers
# ----------------------------------------------------------------------
def _track_payments(request: Request, booking: Booking, purpose: str) -> Response:
    if request.method == "GET":
        rows = Payment.objects.filter(booking=booking, purpose=purpose).order_by("-created_at")
        return Response(PaymentSerializer(rows, many=True).data)
    # POST — record a manual payment. Born PENDING, always: settlement goes
    # through `:mark-paid`/`:capture` so every status change carries a
    # PaymentEvent and fires the booking-advance signals.
    serializer = ManualPaymentCreateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    # _service_call surfaces the one-active-row-per-purpose IntegrityError as
    # a 409 conflict (void or settle the existing row first), not a 500.
    payment = _service_call(
        lambda: ManualPaymentService.record(
            booking=booking,
            purpose=purpose,
            amount=data["amount"],
            provider=data["provider"],
            provider_reference=data["provider_reference"],
            payment_method=data["payment_method"],
            due_at=data["due_at"],
            meta=data["meta"],
            actor=request.user,
            idempotency_key=data["idempotency_key"] or None,
        )
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
        raise NoPendingPayment("No pending payment to action")
    if action == "mark-paid":
        amount = _parse_positive_decimal(request.data.get("amount", pending.amount))
        paid_at = _parse_datetime(
            request.data.get("paid_at", timezone.now().isoformat()), field="paid_at"
        )
        method = request.data.get("method", PaymentMethod.BANK_TRANSFER.value)
        reference = request.data.get("reference", "")
        _service_call(
            lambda: pending.mark_paid(
                amount=amount,
                paid_at=paid_at,
                method=method,
                reference=reference,
                notes=request.data.get("notes", ""),
                actor=request.user,
            )
        )
        return _track_response(booking, purpose)
    if action == "waive":
        _service_call(
            lambda: pending.waive(reason=request.data.get("reason", ""), actor=request.user)
        )
        return _track_response(booking, purpose)
    raise UnknownAction(f"Unknown action {action!r}")
