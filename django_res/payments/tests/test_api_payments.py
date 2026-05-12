"""API tests for flat /payments list + detail."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.enums import StaffRole
from accounts.models import User
from payments.enums import PaymentPurpose, PaymentStatus
from payments.models import Payment
from pricing.models import Currency
from reservations.models import Booking


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="acc-staff@example.com",
        password="x",
        role=StaffRole.ACCOUNTS,
    )


@pytest.mark.django_db
def test_list_payments(api_client: APIClient, staff: User, booking: Booking, gbp: Currency) -> None:
    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("100"),
        currency=gbp,
    )
    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.BALANCE.value,
        amount=Decimal("200"),
        currency=gbp,
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/payments")
    assert response.status_code == 200
    assert response.data["count"] == 2


@pytest.mark.django_db
def test_list_payments__filter_by_purpose(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("100"),
        currency=gbp,
    )
    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.BALANCE.value,
        amount=Decimal("200"),
        currency=gbp,
    )
    api_client.force_login(staff)

    response = api_client.get("/api/v1/payments", {"purpose": "deposit"})
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["results"][0]["purpose"] == "deposit"


@pytest.mark.django_db
def test_retrieve_payment(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("123"),
        currency=gbp,
        status=PaymentStatus.SUCCEEDED.value,
    )
    api_client.force_login(staff)

    response = api_client.get(f"/api/v1/payments/{payment.pk}")
    assert response.status_code == 200
    assert response.data["reference"] == payment.reference
    assert response.data["status"] == PaymentStatus.SUCCEEDED.value
