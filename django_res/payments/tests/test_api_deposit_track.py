"""API tests for the deposit track endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from payments.enums import PaymentPurpose, PaymentStatus
from payments.models import Payment
from pricing.models import Currency
from reservations.models import Booking


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def accounts_user(db: None) -> User:
    return User.objects.create_user(
        email="acc@example.com",
        password="x",
        role=StaffRole.ACCOUNTS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        email="viewer-deposit@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def deposit_payment(db: None, booking: Booking, gbp: Currency) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("420.00"),
        currency=gbp,
        status=PaymentStatus.PENDING.value,
    )


@pytest.mark.django_db
def test_get_deposit_track(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    deposit_payment: Payment,
) -> None:
    api_client.force_login(accounts_user)

    response = api_client.get(f"/api/v1/bookings/{booking.pk}/deposit")
    assert response.status_code == 200
    # The FE Zod schema expects decimal amounts as strings (DRF's default
    # for DecimalField when rendered through a serializer). Pin the shape
    # so a regression to raw `Decimal -> JSON number` is caught.
    assert isinstance(response.data["scheduled_amount"], str)
    assert isinstance(response.data["paid_amount"], str)
    assert Decimal(response.data["scheduled_amount"]) == Decimal("420.00")
    assert Decimal(response.data["paid_amount"]) == Decimal("0")


@pytest.mark.django_db
def test_list_deposit_payments(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    deposit_payment: Payment,
) -> None:
    api_client.force_login(accounts_user)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}/deposit/payments")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["reference"] == deposit_payment.reference


@pytest.mark.django_db
def test_mark_paid_advances_status(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    deposit_payment: Payment,
) -> None:
    api_client.force_login(accounts_user)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/deposit:mark-paid",
        {
            "amount": "420.00",
            "paid_at": "2026-04-12T10:00:00+00:00",
            "method": "bank_transfer",
            "reference": "TXN-001",
        },
        format="json",
    )
    assert response.status_code == 200, response.data
    deposit_payment.refresh_from_db()
    assert deposit_payment.status == PaymentStatus.SUCCEEDED.value


@pytest.mark.django_db
def test_waive_transitions_pending_payment(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    deposit_payment: Payment,
) -> None:
    api_client.force_login(accounts_user)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/deposit:waive",
        {"reason": "owner concession"},
        format="json",
    )
    assert response.status_code == 200
    deposit_payment.refresh_from_db()
    assert deposit_payment.status == PaymentStatus.WAIVED.value


@pytest.mark.django_db
def test_request_payment_returns_501(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    deposit_payment: Payment,
) -> None:
    api_client.force_login(accounts_user)
    response = api_client.post(f"/api/v1/bookings/{booking.pk}/deposit:request-payment")
    assert response.status_code == 501


@pytest.mark.django_db
def test_viewer_cannot_mark_paid(
    api_client: APIClient,
    viewer: User,
    booking: Booking,
    deposit_payment: Payment,
) -> None:
    api_client.force_login(viewer)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/deposit:mark-paid",
        {"amount": "420.00", "paid_at": "2026-04-12T10:00:00+00:00", "method": "bank_transfer"},
        format="json",
    )
    assert response.status_code == 403
