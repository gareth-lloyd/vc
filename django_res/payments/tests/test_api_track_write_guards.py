"""Write-surface guards for the track endpoints.

The track write surface previously trusted the client: a manual payment could
be born SUCCEEDED (no PaymentEvent, no signal, counted by `paid_amount`),
amounts could be negative or garbage, and service `ValueError`s surfaced as
500s. These tests pin the hardened behaviour.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from payments.enums import (
    PaymentPurpose,
    PaymentStatus,
    SecurityDepositKind,
    SecurityDepositStatus,
)
from payments.models import Payment, SecurityDeposit
from pricing.models import Currency
from reservations.models import Booking


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def accounts_user(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="acc-guards@example.com",
        password="x",
        role=StaffRole.ACCOUNTS,
    )


@pytest.fixture
def pending_deposit(db: None, booking: Booking, gbp: Currency) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("420.00"),
        currency=gbp,
        status=PaymentStatus.PENDING.value,
    )


# ----------------------------------------------------------------------
# POST /bookings/{id}/{track}/payments — manual payment creation
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_manual_payment_cannot_be_born_succeeded(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
) -> None:
    """Client-supplied `status` is rejected — a SUCCEEDED row with no
    PaymentEvent, no signal and no audit must be impossible to mint."""
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/deposit/payments",
        {"amount": "100.00", "status": PaymentStatus.SUCCEEDED.value},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert Payment.objects.filter(booking=booking).count() == 0


@pytest.mark.django_db
def test_manual_payment_is_born_pending_and_validated(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
) -> None:
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/deposit/payments",
        {"amount": "100.00", "payment_method": "bank_transfer"},
        format="json",
    )

    assert response.status_code == 201, response.data
    payment = Payment.objects.get(booking=booking)
    assert payment.status == PaymentStatus.PENDING.value
    assert payment.amount == Decimal("100.00")


@pytest.mark.django_db
@pytest.mark.parametrize("amount", ["-100.00", "0", "not-a-number"])
def test_manual_payment_rejects_bad_amounts(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    amount: str,
) -> None:
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/deposit/payments",
        {"amount": amount},
        format="json",
    )

    assert response.status_code == 400, response.data
    assert Payment.objects.filter(booking=booking).count() == 0


@pytest.mark.django_db
def test_manual_payment_rejects_unknown_provider_and_method(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
) -> None:
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/deposit/payments",
        {"amount": "100.00", "provider": "venmo", "payment_method": "iou"},
        format="json",
    )

    assert response.status_code == 400, response.data


@pytest.mark.django_db
def test_second_active_payment_is_409_not_500(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    pending_deposit: Payment,
) -> None:
    """The one-active-DEPOSIT-per-booking constraint must surface as a
    conflict, not an unhandled IntegrityError."""
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/deposit/payments",
        {"amount": "50.00"},
        format="json",
    )

    assert response.status_code == 409, response.data


# ----------------------------------------------------------------------
# PATCH /bookings/{id}/{track} and :mark-paid — amount bounds
# ----------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("amount", ["-420.00", "nonsense"])
def test_patch_track_rejects_bad_amounts(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    pending_deposit: Payment,
    amount: str,
) -> None:
    api_client.force_login(accounts_user)

    response = api_client.patch(
        f"/api/v1/bookings/{booking.pk}/deposit",
        {"amount": amount},
        format="json",
    )

    assert response.status_code == 400, response.data
    pending_deposit.refresh_from_db()
    assert pending_deposit.amount == Decimal("420.00")


@pytest.mark.django_db
@pytest.mark.parametrize("amount", ["-1.00", "0"])
def test_mark_paid_rejects_non_positive_amounts(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    pending_deposit: Payment,
    amount: str,
) -> None:
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/deposit:mark-paid",
        {"amount": amount, "paid_at": timezone.now().isoformat()},
        format="json",
    )

    assert response.status_code == 400, response.data
    pending_deposit.refresh_from_db()
    assert pending_deposit.status == PaymentStatus.PENDING.value


# ----------------------------------------------------------------------
# Security track — claim bounds, active-SD lookup, error shape
# ----------------------------------------------------------------------


@pytest.fixture
def held_bt_sd(db: None, booking: Booking, gbp: Currency) -> SecurityDeposit:
    return SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.BT_REFUNDABLE.value,
        status=SecurityDepositStatus.HELD.value,
        amount=Decimal("500.00"),
        currency=gbp,
    )


@pytest.mark.django_db
@pytest.mark.parametrize("captured", ["600.00", "-50.00"])
def test_claim_bt_bounds_captured_amount(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    held_bt_sd: SecurityDeposit,
    gbp: Currency,
    captured: str,
) -> None:
    """BT-path claim must bound 0 <= captured_amount <= sd.amount — a
    captured_amount above the deposit produced a negative refunded_amount."""
    sd_payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=PaymentStatus.SUCCEEDED.value,
    )
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security/payments/{sd_payment.pk}:claim",
        {"captured_amount": captured},
        format="json",
    )

    assert response.status_code in (400, 409), response.data
    held_bt_sd.refresh_from_db()
    assert held_bt_sd.status == SecurityDepositStatus.HELD.value


@pytest.mark.django_db
def test_captured_sd_is_not_served_as_active(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
) -> None:
    """CAPTURED and PARTIALLY_REFUNDED are terminal — actions against them
    must 409 with no_active_sd, not hit raw ValueErrors downstream."""
    SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        status=SecurityDepositStatus.CAPTURED.value,
        amount=Decimal("500.00"),
        currency=gbp,
    )
    sd_payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=PaymentStatus.SUCCEEDED.value,
    )
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security/payments/{sd_payment.pk}:release",
        {},
        format="json",
    )

    assert response.status_code == 409, response.data
    assert response.data["code"] == "no_active_sd"


@pytest.mark.django_db
def test_security_mark_paid_without_amount_is_400_not_500(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
) -> None:
    SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.BT_REFUNDABLE.value,
        status=SecurityDepositStatus.AWAITING_BT.value,
        amount=Decimal("500.00"),
        currency=gbp,
    )
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security:mark-paid",
        {},
        format="json",
    )

    assert response.status_code == 400, response.data


@pytest.mark.django_db
def test_sd_service_state_mismatch_is_409_not_500(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
) -> None:
    """`:hold` on a BT-kind SD raises a service ValueError — must be a 409."""
    SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.BT_REFUNDABLE.value,
        status=SecurityDepositStatus.AWAITING_BT.value,
        amount=Decimal("500.00"),
        currency=gbp,
    )
    sd_payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=PaymentStatus.PENDING.value,
    )
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security/payments/{sd_payment.pk}:hold",
        {"gateway_response": {}},
        format="json",
    )

    assert response.status_code == 409, response.data


@pytest.mark.django_db
def test_sd_double_hold_is_409_not_500(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
) -> None:
    """A second :hold races the one-active-SD-payment constraint — the
    IntegrityError must surface as a conflict, not a 500."""
    SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        status=SecurityDepositStatus.AWAITING_DETAILS.value,
        amount=Decimal("500.00"),
        currency=gbp,
    )
    # FAILED so the URL anchor doesn't occupy the active-SD-payment slot.
    sd_payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=PaymentStatus.FAILED.value,
    )
    api_client.force_login(accounts_user)
    url = f"/api/v1/bookings/{booking.pk}/security/payments/{sd_payment.pk}:hold"

    first = api_client.post(url, {"gateway_response": {}}, format="json")
    assert first.status_code == 200, first.data

    second = api_client.post(url, {"gateway_response": {}}, format="json")
    assert second.status_code == 409, second.data
