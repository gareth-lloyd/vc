"""API tests for the security-deposit track endpoints."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from payments.enums import SecurityDepositKind, SecurityDepositStatus
from payments.models import SecurityDeposit
from pricing.models import Currency
from reservations.models import Booking


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def accounts_user(db: None) -> User:
    return User.objects.create_user(
        email="sd-acc@example.com",
        password="x",
        role=StaffRole.ACCOUNTS,
    )


@pytest.fixture
def sd_preauth(db: None, booking: Booking, gbp: Currency) -> SecurityDeposit:
    return SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.AWAITING_DETAILS.value,
    )


@pytest.mark.django_db
def test_hold_then_release(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    sd_preauth: SecurityDeposit,
) -> None:
    api_client.force_login(accounts_user)

    # The :hold action lives on the per-payment URL but the active SD is what
    # the service consumes. payment_pk is arbitrary in this test — the lookup
    # resolves via SecurityDepositService internals.
    hold = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security/payments/1:hold",
        {"gateway_response": {"hold_expires_at": None, "provider_reference": "AUTH-1"}},
        format="json",
    )
    assert hold.status_code == 200, hold.data
    sd_preauth.refresh_from_db()
    assert sd_preauth.status == SecurityDepositStatus.PRE_AUTHED.value

    release = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security/payments/1:release",
    )
    assert release.status_code == 200
    sd_preauth.refresh_from_db()
    assert sd_preauth.status == SecurityDepositStatus.RELEASED.value


@pytest.mark.django_db
def test_get_security_track(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    sd_preauth: SecurityDeposit,
) -> None:
    api_client.force_login(accounts_user)
    response = api_client.get(f"/api/v1/bookings/{booking.pk}/security")
    assert response.status_code == 200
    assert response.data["booking"] == booking.pk
