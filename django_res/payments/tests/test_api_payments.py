"""API tests for flat /payments list + detail."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.enums import StaffRole
from accounts.models import User
from core.tests import assert_max_queries
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
def test_list_payments__bounded_query_count(
    api_client: APIClient, staff: User, booking: Booking, gbp: Currency
) -> None:
    """Pin PaymentViewSet against N+1: query count must stay flat as rows grow.

    The list endpoint serialises FKs (`booking`, `currency`, `concierge_item`)
    as PKs, and `get_queryset` calls `select_related` on them so the dispatch
    cost is constant. Without `select_related`, this assertion fails because
    each Payment row triggers an extra SELECT for its FKs once any serializer
    field walks them.
    """
    # FAILED is not in `ACTIVE_PAYMENT_STATUSES`, so the unique-active-deposit
    # constraint doesn't block creating multiple rows for the same booking.
    for _ in range(10):
        Payment.objects.create(
            booking=booking,
            purpose=PaymentPurpose.DEPOSIT.value,
            status=PaymentStatus.FAILED.value,
            amount=Decimal("10"),
            currency=gbp,
        )
    api_client.force_login(staff)

    # Warm any per-test session caches so the bound reflects steady-state
    # query cost, not first-request cold-start overhead.
    api_client.get("/api/v1/payments")

    with assert_max_queries(5):
        response = api_client.get("/api/v1/payments")
    assert response.status_code == 200
    assert response.data["count"] == 10


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
