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
