"""API tests for the dedicated security-deposit read endpoint.

`GET /bookings/{id}/security/deposit` returns the booking's most-recent
`SecurityDeposit` row (incl. terminal states) serialized through
`SecurityDepositSerializer`, or `null` when none exists. Distinct from the
Payment-aggregate `/security` track — this exposes the SD row's own
`kind`/`status`/`captured_amount`/`damage_claim` fields the wf-8 panel renders.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
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
        is_staff=True,
        email="sd-detail-acc@example.com",
        password="x",
        role=StaffRole.ACCOUNTS,
    )


def _url(booking: Booking) -> str:
    return f"/api/v1/bookings/{booking.pk}/security/deposit"


@pytest.mark.django_db
def test_returns_null_when_no_security_deposit(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
) -> None:
    api_client.force_login(accounts_user)
    response = api_client.get(_url(booking))
    assert response.status_code == 200, response.data
    assert response.data is None


@pytest.mark.django_db
def test_returns_full_sd_fields_for_pre_auth_hold(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
) -> None:
    sd = SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.PRE_AUTHED.value,
    )
    api_client.force_login(accounts_user)
    response = api_client.get(_url(booking))
    assert response.status_code == 200, response.data
    data = response.data
    assert data["id"] == sd.pk
    assert data["reference"] == sd.reference
    assert data["kind"] == SecurityDepositKind.PRE_AUTH_HOLD.value
    assert data["status"] == SecurityDepositStatus.PRE_AUTHED.value
    assert data["amount"] == "500.00"
    assert data["currency_code"] == gbp.code
    assert data["captured_amount"] is None
    assert data["refunded_amount"] is None
    assert data["damage_claim"] is None
    # release_scheduled_for is a DateField — absent here, but the key must exist.
    assert "release_scheduled_for" in data
    assert "hold_expires_at" in data
    assert "due_at" in data


@pytest.mark.django_db
def test_returns_most_recent_including_terminal(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
) -> None:
    """A released/captured SD is still the truth to show — the panel renders
    the final state, so the read returns the most-recent row regardless of
    terminal status (unlike `_get_active_sd`, which excludes terminals)."""
    SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.CAPTURED.value,
        captured_amount=Decimal("120.00"),
    )
    api_client.force_login(accounts_user)
    response = api_client.get(_url(booking))
    assert response.status_code == 200, response.data
    assert response.data["status"] == SecurityDepositStatus.CAPTURED.value
    assert response.data["captured_amount"] == "120.00"


@pytest.mark.django_db
@pytest.mark.parametrize("role", [StaffRole.VIEWER, StaffRole.RESERVATIONS])
def test_any_staff_may_read(
    api_client: APIClient,
    booking: Booking,
    role: StaffRole,
) -> None:
    """`IsAccountsWriter` permits all-staff reads (SAFE_METHODS) — same as the
    sibling `/security` track GET. The accounts gate bites on the *write*
    actions (`:release`/`:claim`), not the read; the FE disables those buttons
    for non-accounts staff rather than hiding the whole panel."""
    user = User.objects.create_user(
        is_staff=True,
        email=f"sd-detail-{role.value}@example.com",
        password="x",
        role=role,
    )
    api_client.force_login(user)
    response = api_client.get(_url(booking))
    assert response.status_code == 200, response.data


@pytest.mark.django_db
def test_anonymous_is_forbidden(
    api_client: APIClient,
    booking: Booking,
) -> None:
    response = api_client.get(_url(booking))
    assert response.status_code in (401, 403), response.data


@pytest.mark.django_db
def test_query_count_is_bounded(
    api_client: APIClient,
    accounts_user: User,
    booking: Booking,
    gbp: Currency,
) -> None:
    SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.PRE_AUTHED.value,
    )
    api_client.force_login(accounts_user)
    with assert_max_queries(6):
        api_client.get(_url(booking))
