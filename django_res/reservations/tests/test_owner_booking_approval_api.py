"""API tests for owner booking approve/decline + the can_approve flag."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import cast

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.factories import UserFactory
from accounts.models import User
from owners.enums import OwnerMembershipStatus, OwnerRole
from owners.factories import (
    OwnerMembershipFactory,
    OwnerOrganisationFactory,
    OwnerOrgPropertyFactory,
)
from owners.models import OwnerOrganisation
from pricing.models import Currency
from properties.models import Property
from reservations.enums import BookingStatus, PaymentMethod
from reservations.models import Booking, Guest, Quotation, QuotationLine, TermsVersion
from reservations.signals import booking_transitioned

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def _owner(org: OwnerOrganisation, role: OwnerRole = OwnerRole.ADMIN) -> User:
    user = cast(User, UserFactory(is_staff=False))
    OwnerMembershipFactory(
        organisation=org, user=user, role=role, status=OwnerMembershipStatus.ACTIVE
    )
    return user


def _pending_booking(
    property_: Property, gbp: Currency, terms: TermsVersion, guest: Guest
) -> Booking:
    start = timezone.localdate() + timedelta(days=30)
    end = start + timedelta(days=7)
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=start,
        date_to=end,
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property_,
        date_from=start,
        date_to=end,
        adults=2,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        status=BookingStatus.PENDING_OWNER_APPROVAL.value,
    )


def test_admin_owner_approves(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    OwnerOrgPropertyFactory(organisation=org, property=property_)
    booking = _pending_booking(property_, gbp, terms, guest)
    api_client.force_authenticate(user)

    captured: list[tuple[str, str]] = []

    def _receiver(sender: object, **kwargs: object) -> None:
        captured.append((str(kwargs["from_status"]), str(kwargs["to_status"])))

    booking_transitioned.connect(_receiver, dispatch_uid="test-owner-approve")
    try:
        resp = api_client.post(f"/api/v1/owner/bookings/{booking.id}:approve", format="json")
    finally:
        booking_transitioned.disconnect(dispatch_uid="test-owner-approve")

    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == BookingStatus.AWAITING_DEPOSIT.value
    # The transition fired the signal that drives guest lifecycle comms.
    assert captured == [
        (BookingStatus.PENDING_OWNER_APPROVAL.value, BookingStatus.AWAITING_DEPOSIT.value)
    ]


def test_approve_rolls_back_transition_when_payment_scheduling_fails(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    """If the payments receiver raises, the approve transition rolls back.

    `booking_transitioned` is dispatched after `_transition` commits its own
    atomic block, so the approve view must wrap `owner_approve()` in a
    transaction — otherwise a payment-scheduling failure would leave the booking
    committed in AWAITING_DEPOSIT with no payment rows and wedge any retry on
    InvalidTransition. The booking must stay PENDING_OWNER_APPROVAL.
    """
    from unittest.mock import patch

    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    OwnerOrgPropertyFactory(organisation=org, property=property_)
    booking = _pending_booking(property_, gbp, terms, guest)
    api_client.force_authenticate(user)

    with patch(
        "payments.services.payment_scheduler.PaymentScheduler.create_for_booking",
        side_effect=RuntimeError("scheduler boom"),
    ):
        with pytest.raises(RuntimeError, match="scheduler boom"):
            api_client.post(f"/api/v1/owner/bookings/{booking.id}:approve", format="json")

    booking.refresh_from_db()
    assert booking.status == BookingStatus.PENDING_OWNER_APPROVAL.value


def test_decline_requires_reason(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    OwnerOrgPropertyFactory(organisation=org, property=property_)
    booking = _pending_booking(property_, gbp, terms, guest)
    api_client.force_authenticate(user)

    resp = api_client.post(f"/api/v1/owner/bookings/{booking.id}:decline", format="json")
    assert resp.status_code == 400
    assert "reason" in resp.json()["field_errors"]


def test_decline_with_reason(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    OwnerOrgPropertyFactory(organisation=org, property=property_)
    booking = _pending_booking(property_, gbp, terms, guest)
    api_client.force_authenticate(user)

    resp = api_client.post(
        f"/api/v1/owner/bookings/{booking.id}:decline",
        data={"reason": "Villa unavailable that week"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert resp.json()["status"] == BookingStatus.DECLINED.value


def test_editor_cannot_approve(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org, role=OwnerRole.EDITOR)
    OwnerOrgPropertyFactory(organisation=org, property=property_)
    booking = _pending_booking(property_, gbp, terms, guest)
    api_client.force_authenticate(user)

    resp = api_client.post(f"/api/v1/owner/bookings/{booking.id}:approve", format="json")
    assert resp.status_code == 403


def test_wrong_status_409s(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    OwnerOrgPropertyFactory(organisation=org, property=property_)
    booking = _pending_booking(property_, gbp, terms, guest)
    booking.owner_approve()  # already moved to AWAITING_DEPOSIT
    api_client.force_authenticate(user)

    resp = api_client.post(f"/api/v1/owner/bookings/{booking.id}:approve", format="json")
    assert resp.status_code == 409


def test_can_approve_flag_true_for_admin(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org)
    OwnerOrgPropertyFactory(organisation=org, property=property_)
    booking = _pending_booking(property_, gbp, terms, guest)
    api_client.force_authenticate(user)

    body = api_client.get(f"/api/v1/owner/bookings/{booking.id}").json()
    assert body["can_approve"] is True


def test_can_approve_flag_false_for_view_only(
    api_client: APIClient, gbp: Currency, terms: TermsVersion, guest: Guest, property_: Property
) -> None:
    org = cast(OwnerOrganisation, OwnerOrganisationFactory())
    user = _owner(org, role=OwnerRole.VIEW_ONLY)
    OwnerOrgPropertyFactory(organisation=org, property=property_)
    booking = _pending_booking(property_, gbp, terms, guest)
    api_client.force_authenticate(user)

    body = api_client.get(f"/api/v1/owner/bookings/{booking.id}").json()
    assert body["can_approve"] is False
