"""URL routes for the payments API surface."""

from __future__ import annotations

from django.urls import URLPattern, URLResolver, include, path
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from core.api.permissions import IsAccountsWriter
from payments.views import (
    PaymentViewSet,
    RefundViewSet,
    balance_payments,
    balance_track,
    balance_track_action,
    deposit_payments,
    deposit_track,
    deposit_track_action,
    payment_action,
    security_payment_action,
    security_payments,
    security_track,
    security_track_action,
    webhook_view,
)
from payments.views.refund import list_refunds_for_booking, request_refund_for_booking


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated, IsAccountsWriter])
def refunds_for_booking(request: Request, booking_pk: int) -> Response:
    """Dispatcher for `/bookings/{id}/refunds`."""
    if request.method == "GET":
        return list_refunds_for_booking(request, booking_pk)
    return request_refund_for_booking(request, booking_pk)


_router = SimpleRouter(trailing_slash=False)
_router.register("payments", PaymentViewSet, basename="payment")
_router.register("refunds", RefundViewSet, basename="refund")


_refund_actions: list[URLPattern | URLResolver] = [
    path(
        "refunds/<int:pk>:approve",
        RefundViewSet.as_view({"post": "approve"}),
        name="refund-approve",
    ),
    path(
        "refunds/<int:pk>:reject",
        RefundViewSet.as_view({"post": "reject"}),
        name="refund-reject",
    ),
    path(
        "refunds/<int:pk>:execute",
        RefundViewSet.as_view({"post": "execute"}),
        name="refund-execute",
    ),
    path(
        "refunds/<int:pk>:cancel",
        RefundViewSet.as_view({"post": "cancel"}),
        name="refund-cancel",
    ),
    path(
        "bookings/<int:booking_pk>/refunds",
        refunds_for_booking,
        name="booking-refunds",
    ),
]


# Deposit track
_deposit_routes: list[URLPattern | URLResolver] = [
    path("bookings/<int:booking_pk>/deposit", deposit_track, name="booking-deposit"),
    path(
        "bookings/<int:booking_pk>/deposit/payments",
        deposit_payments,
        name="booking-deposit-payments",
    ),
    path(
        "bookings/<int:booking_pk>/deposit/payments/<int:payment_pk>:capture",
        lambda request, booking_pk, payment_pk: payment_action(
            request, booking_pk, "deposit", payment_pk, "capture"
        ),
        name="booking-deposit-payment-capture",
    ),
    path(
        "bookings/<int:booking_pk>/deposit/payments/<int:payment_pk>:void",
        lambda request, booking_pk, payment_pk: payment_action(
            request, booking_pk, "deposit", payment_pk, "void"
        ),
        name="booking-deposit-payment-void",
    ),
    path(
        "bookings/<int:booking_pk>/deposit:request-payment",
        lambda request, booking_pk: deposit_track_action(request, booking_pk, "request-payment"),
        name="booking-deposit-request-payment",
    ),
    path(
        "bookings/<int:booking_pk>/deposit:mark-paid",
        lambda request, booking_pk: deposit_track_action(request, booking_pk, "mark-paid"),
        name="booking-deposit-mark-paid",
    ),
    path(
        "bookings/<int:booking_pk>/deposit:waive",
        lambda request, booking_pk: deposit_track_action(request, booking_pk, "waive"),
        name="booking-deposit-waive",
    ),
]


# Balance track
_balance_routes: list[URLPattern | URLResolver] = [
    path("bookings/<int:booking_pk>/balance", balance_track, name="booking-balance"),
    path(
        "bookings/<int:booking_pk>/balance/payments",
        balance_payments,
        name="booking-balance-payments",
    ),
    path(
        "bookings/<int:booking_pk>/balance/payments/<int:payment_pk>:capture",
        lambda request, booking_pk, payment_pk: payment_action(
            request, booking_pk, "balance", payment_pk, "capture"
        ),
        name="booking-balance-payment-capture",
    ),
    path(
        "bookings/<int:booking_pk>/balance/payments/<int:payment_pk>:void",
        lambda request, booking_pk, payment_pk: payment_action(
            request, booking_pk, "balance", payment_pk, "void"
        ),
        name="booking-balance-payment-void",
    ),
    path(
        "bookings/<int:booking_pk>/balance:request-payment",
        lambda request, booking_pk: balance_track_action(request, booking_pk, "request-payment"),
        name="booking-balance-request-payment",
    ),
    path(
        "bookings/<int:booking_pk>/balance:mark-paid",
        lambda request, booking_pk: balance_track_action(request, booking_pk, "mark-paid"),
        name="booking-balance-mark-paid",
    ),
    path(
        "bookings/<int:booking_pk>/balance:waive",
        lambda request, booking_pk: balance_track_action(request, booking_pk, "waive"),
        name="booking-balance-waive",
    ),
]


# Security deposit track
_security_routes: list[URLPattern | URLResolver] = [
    path("bookings/<int:booking_pk>/security", security_track, name="booking-security"),
    path(
        "bookings/<int:booking_pk>/security/payments",
        security_payments,
        name="booking-security-payments",
    ),
    path(
        "bookings/<int:booking_pk>/security/payments/<int:payment_pk>:capture",
        lambda request, booking_pk, payment_pk: security_payment_action(
            request, booking_pk, payment_pk, "capture"
        ),
        name="booking-security-payment-capture",
    ),
    path(
        "bookings/<int:booking_pk>/security/payments/<int:payment_pk>:hold",
        lambda request, booking_pk, payment_pk: security_payment_action(
            request, booking_pk, payment_pk, "hold"
        ),
        name="booking-security-payment-hold",
    ),
    path(
        "bookings/<int:booking_pk>/security/payments/<int:payment_pk>:release",
        lambda request, booking_pk, payment_pk: security_payment_action(
            request, booking_pk, payment_pk, "release"
        ),
        name="booking-security-payment-release",
    ),
    path(
        "bookings/<int:booking_pk>/security/payments/<int:payment_pk>:claim",
        lambda request, booking_pk, payment_pk: security_payment_action(
            request, booking_pk, payment_pk, "claim"
        ),
        name="booking-security-payment-claim",
    ),
    path(
        "bookings/<int:booking_pk>/security:request-payment",
        lambda request, booking_pk: security_track_action(request, booking_pk, "request-payment"),
        name="booking-security-request-payment",
    ),
    path(
        "bookings/<int:booking_pk>/security:mark-paid",
        lambda request, booking_pk: security_track_action(request, booking_pk, "mark-paid"),
        name="booking-security-mark-paid",
    ),
]


urlpatterns: list[URLPattern | URLResolver] = [
    # Action endpoints come BEFORE the router so the router's `<pk>` pattern
    # (which defaults to `[^/.]+`, greedy enough to swallow `1:approve` as a
    # single pk) can't short-circuit the colon-verb routes.
    *_refund_actions,
    *_deposit_routes,
    *_balance_routes,
    *_security_routes,
    path("", include(_router.urls)),
    # Webhook ingest (existing).
    path(
        "webhooks/payments/<str:provider_slug>/",
        csrf_exempt(webhook_view),
        name="payments-webhook",
    ),
]
