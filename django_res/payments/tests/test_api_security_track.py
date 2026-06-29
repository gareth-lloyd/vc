"""API tests for the security-deposit track endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, cast

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from payments.enums import SecurityDepositKind, SecurityDepositStatus
from payments.models import SecurityDeposit
from pricing.models import Currency
from reservations.models import Booking

if TYPE_CHECKING:
    from accounts.models import Person
    from properties.models import Property
    from reservations.models import DamageClaim, TermsVersion


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def accounts_user(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
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

    # :hold stays per-payment (deferred Flywire); the active SD is what the
    # service consumes, so payment_pk is arbitrary — the lookup resolves via
    # SecurityDepositService internals. :release is now track-level (2B).
    hold = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security/payments/1:hold",
        {"gateway_response": {"hold_expires_at": None, "provider_reference": "AUTH-1"}},
        format="json",
    )
    assert hold.status_code == 200, hold.data
    sd_preauth.refresh_from_db()
    assert sd_preauth.status == SecurityDepositStatus.PRE_AUTHED.value

    release = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security:release",
    )
    assert release.status_code == 200
    sd_preauth.refresh_from_db()
    assert sd_preauth.status == SecurityDepositStatus.RELEASED.value


@pytest.fixture
def sd_bt(db: None, booking: Booking, gbp: Currency) -> SecurityDeposit:
    return SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.BT_REFUNDABLE.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.AWAITING_BT.value,
    )


@pytest.mark.django_db
def test_mark_paid_against_pre_auth_sd_is_409_with_stable_code(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    sd_preauth: SecurityDeposit,
) -> None:
    """`:mark-paid` only applies to BT_REFUNDABLE — a PRE_AUTH_HOLD SD must
    refuse with a kind-specific 409, never a 500 (BUG-011).
    """
    api_client.force_login(accounts_user)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security:mark-paid",
        {"amount": "500.00", "paid_at": "2026-06-01T10:00:00Z"},
        format="json",
    )
    assert response.status_code == 409, response.data
    assert response.data["code"] == "invalid_sd_kind"
    sd_preauth.refresh_from_db()
    assert sd_preauth.status == SecurityDepositStatus.AWAITING_DETAILS.value


@pytest.mark.django_db
def test_hold_against_bt_sd_is_409_with_stable_code(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    sd_bt: SecurityDeposit,
) -> None:
    """`:hold` only applies to PRE_AUTH_HOLD — a BT_REFUNDABLE SD must refuse
    with a kind-specific 409, never a 500 (BUG-011).
    """
    api_client.force_login(accounts_user)
    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security/payments/1:hold",
        {"gateway_response": {}},
        format="json",
    )
    assert response.status_code == 409, response.data
    assert response.data["code"] == "invalid_sd_kind"
    sd_bt.refresh_from_db()
    assert sd_bt.status == SecurityDepositStatus.AWAITING_BT.value


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


@pytest.fixture
def sd_preauthed(db: None, booking: Booking, gbp: Currency) -> SecurityDeposit:
    return SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.PRE_AUTHED.value,
    )


@pytest.mark.django_db
def test_track_level_claim_links_damage_claim_and_captures(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
    sd_preauthed: SecurityDeposit,
) -> None:
    """Track-level `:claim` (relocated in 2B) links the DamageClaim and writes
    captured_amount: PRE_AUTHED → CAPTURED."""
    from reservations.factories import DamageClaimFactory

    claim = cast(
        "DamageClaim",
        DamageClaimFactory(booking=booking, currency=gbp, amount=Decimal("120.00")),
    )
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security:claim",
        {"damage_claim": claim.pk, "captured_amount": "120.00"},
        format="json",
    )

    assert response.status_code == 200, response.data
    sd_preauthed.refresh_from_db()
    assert sd_preauthed.status == SecurityDepositStatus.CAPTURED.value
    assert sd_preauthed.captured_amount == Decimal("120.00")
    assert sd_preauthed.damage_claim_id == claim.pk


@pytest.mark.django_db
def test_track_level_claim_defaults_captured_amount_to_full(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
    sd_preauthed: SecurityDeposit,
) -> None:
    """No captured_amount in the body → defaults to the full SD amount."""
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security:claim",
        {},
        format="json",
    )

    assert response.status_code == 200, response.data
    sd_preauthed.refresh_from_db()
    assert sd_preauthed.status == SecurityDepositStatus.CAPTURED.value
    assert sd_preauthed.captured_amount == Decimal("500.00")


@pytest.mark.django_db
def test_track_level_claim_wrong_booking_is_400(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
    property_: Property,
    customer: Person,
    terms: TermsVersion,
    sd_preauthed: SecurityDeposit,
) -> None:
    """A DamageClaim from another booking → 400, not a 500 FK violation."""
    from datetime import date, timedelta

    from reservations.factories import DamageClaimFactory, make_occupying_booking

    other_booking = make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date.today() + timedelta(days=300),
        date_to=date.today() + timedelta(days=307),
    )
    other_claim = cast("DamageClaim", DamageClaimFactory(booking=other_booking, currency=gbp))
    api_client.force_login(accounts_user)

    response = api_client.post(
        f"/api/v1/bookings/{booking.pk}/security:claim",
        {"damage_claim": other_claim.pk, "captured_amount": "50.00"},
        format="json",
    )

    assert response.status_code == 400, response.data
    sd_preauthed.refresh_from_db()
    assert sd_preauthed.status == SecurityDepositStatus.PRE_AUTHED.value
