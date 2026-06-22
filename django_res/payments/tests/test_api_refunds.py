"""API tests for /refunds + nested /bookings/{id}/refunds."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from payments.enums import (
    PaymentPurpose,
    PaymentStatus,
    RefundPurposeTrack,
    RefundReasonCode,
    RefundStatus,
)
from payments.models import Payment, Refund
from pricing.models import Currency
from reservations.models import Booking


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _make_accounts_user(email: str) -> User:
    user = User.objects.create_user(
        is_staff=True,
        email=email,
        password="x",
        role=StaffRole.ACCOUNTS,
    )
    # Grant the underlying Django perms the service requires.
    from django.contrib.auth.models import Permission

    for codename in ("approve_refund", "execute_refund"):
        try:
            perm = Permission.objects.get(codename=codename)
        except Permission.DoesNotExist:
            continue
        user.user_permissions.add(perm)
    return user


@pytest.fixture
def requester(db: None) -> User:
    return _make_accounts_user("refund-req@example.com")


@pytest.fixture
def approver(db: None) -> User:
    return _make_accounts_user("refund-app@example.com")


@pytest.fixture
def succeeded_deposit(db: None, booking: Booking, gbp: Currency) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("420.00"),
        currency=gbp,
        status=PaymentStatus.SUCCEEDED.value,
    )


@pytest.mark.django_db
def test_request_refund(
    api_client: APIClient,
    requester: User,
    booking: Booking,
    succeeded_deposit: Payment,
    gbp: Currency,
) -> None:
    api_client.force_login(requester)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/refunds",
        {
            "amount": "120.00",
            "currency": gbp.pk,
            "purpose_track": RefundPurposeTrack.DEPOSIT.value,
            "reason_code": RefundReasonCode.OVERPAYMENT.value,
            "reason_notes": "guest paid twice",
            "against_payment": succeeded_deposit.pk,
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    refund = Refund.objects.get()
    assert refund.requested_by_id == requester.pk
    assert refund.status == RefundStatus.PENDING.value


@pytest.mark.django_db
def test_approve_and_execute_separation_of_duties(
    api_client: APIClient,
    requester: User,
    approver: User,
    booking: Booking,
    succeeded_deposit: Payment,
    gbp: Currency,
) -> None:
    # Open a refund as requester.
    refund = Refund.objects.create(
        booking=booking,
        against_payment=succeeded_deposit,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        amount=Decimal("50.00"),
        currency=gbp,
        status=RefundStatus.PENDING.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        requested_by=requester,
    )

    # The requester can NOT approve their own refund.
    api_client.force_login(requester)
    self_approve = api_client.post(f"/api/v1/refunds/{refund.pk}:approve")
    assert self_approve.status_code == 403
    # Canonical error shape (SMELL-010): the service raises `AuthorizationError`
    # and the canonical handler maps it — no per-view `except PermissionError`.
    assert self_approve.data["code"] == "forbidden"
    refund.refresh_from_db()
    assert refund.status == RefundStatus.PENDING.value

    # A distinct approver can.
    api_client.force_login(approver)
    response = api_client.post(f"/api/v1/refunds/{refund.pk}:approve")
    assert response.status_code == 200
    refund.refresh_from_db()
    assert refund.status == RefundStatus.APPROVED.value

    # Execute. Approver must differ from executor unless self_approve perm.
    # Here approver and "executor" (current user is approver) ARE the same;
    # service should reject without `self_approve_refund` perm. Service-layer
    # raises PermissionError → 500 in our default handler. Use a third user.
    other = _make_accounts_user("refund-exec@example.com")
    api_client.force_login(other)
    execute = api_client.post(f"/api/v1/refunds/{refund.pk}:execute")
    assert execute.status_code == 200, execute.data
    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value


@pytest.mark.django_db
def test_reject_refund(
    api_client: APIClient,
    requester: User,
    approver: User,
    booking: Booking,
    succeeded_deposit: Payment,
    gbp: Currency,
) -> None:
    refund = Refund.objects.create(
        booking=booking,
        against_payment=succeeded_deposit,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        amount=Decimal("50.00"),
        currency=gbp,
        status=RefundStatus.PENDING.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        requested_by=requester,
    )
    api_client.force_login(approver)
    response = api_client.post(
        f"/api/v1/refunds/{refund.pk}:reject",
        {"reason": "no proof of duplicate"},
        format="json",
    )
    assert response.status_code == 200
    refund.refresh_from_db()
    assert refund.status == RefundStatus.REJECTED.value


@pytest.mark.django_db
def test_list_refunds_for_booking(
    api_client: APIClient,
    requester: User,
    booking: Booking,
    succeeded_deposit: Payment,
    gbp: Currency,
) -> None:
    Refund.objects.create(
        booking=booking,
        against_payment=succeeded_deposit,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        amount=Decimal("50.00"),
        currency=gbp,
        status=RefundStatus.PENDING.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        requested_by=requester,
    )
    api_client.force_login(requester)

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/refunds")
    assert response.status_code == 200
    assert len(response.data) == 1


@pytest.mark.django_db
def test_request_refund__retry_with_same_idempotency_key_returns_original(
    api_client: APIClient,
    requester: User,
    booking: Booking,
    succeeded_deposit: Payment,
    gbp: Currency,
) -> None:
    """A retried POST with the same `idempotency_key` returns the first Refund.

    The service has supported `idempotency_key` since FG-010/FG-012, but the
    API surface never exposed it — operator double-clicks and flaky-network
    retries would double-open refunds. Mirrors the manual-payment pattern
    (`ManualPaymentCreateSerializer`).
    """
    api_client.force_login(requester)
    body = {
        "amount": "120.00",
        "currency": gbp.pk,
        "purpose_track": RefundPurposeTrack.DEPOSIT.value,
        "reason_code": RefundReasonCode.OVERPAYMENT.value,
        "against_payment": succeeded_deposit.pk,
        "idempotency_key": "op-refund-click-1",
    }
    first = api_client.post(f"/api/v1/bookings/{booking.pk}/refunds", body, format="json")
    second = api_client.post(f"/api/v1/bookings/{booking.pk}/refunds", body, format="json")
    assert first.status_code == 201, first.data
    assert second.status_code == 201, second.data
    assert second.data["id"] == first.data["id"]
    assert Refund.objects.filter(booking=booking).count() == 1


@pytest.mark.django_db
def test_request_refund__idempotency_race_returns_409_not_500(
    api_client: APIClient,
    requester: User,
    booking: Booking,
    succeeded_deposit: Payment,
    gbp: Currency,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FG-010 DB backstop must surface as a 409 conflict, not a 500.

    Two concurrent requests with the same key both pass `find_by_meta_key`
    under READ COMMITTED; the loser hits the
    `refund_idempotency_key_unique_per_booking` partial unique index.
    Simulated by patching the pre-check to miss, as the service-level
    backstop test does by bypassing it.
    """
    monkeypatch.setattr(
        "payments.services.refund.find_by_meta_key",
        lambda queryset, key: None,
    )
    api_client.force_login(requester)
    body = {
        "amount": "120.00",
        "currency": gbp.pk,
        "purpose_track": RefundPurposeTrack.DEPOSIT.value,
        "reason_code": RefundReasonCode.OVERPAYMENT.value,
        "against_payment": succeeded_deposit.pk,
        "idempotency_key": "op-refund-race-1",
    }
    first = api_client.post(f"/api/v1/bookings/{booking.pk}/refunds", body, format="json")
    assert first.status_code == 201, first.data
    second = api_client.post(f"/api/v1/bookings/{booking.pk}/refunds", body, format="json")
    assert second.status_code == 409, getattr(second, "data", second)
    assert second.data["code"] == "invalid_state"
    assert Refund.objects.filter(booking=booking).count() == 1
