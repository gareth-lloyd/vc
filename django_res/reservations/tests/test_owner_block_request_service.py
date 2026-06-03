"""Tests for OwnerBlockRequestService lifecycle + overlap enforcement."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import pytest
from django.utils import timezone

from accounts.factories import UserFactory
from accounts.models import User
from core.exceptions import HoldUnavailable, InvalidTransition, OverlappingBooking
from reservations.enums import (
    BookingHoldReason,
    BookingStatus,
    OwnerBlockKind,
    OwnerBlockRequestStatus,
    PaymentMethod,
)
from reservations.models import Booking, BookingHold, Quotation, QuotationLine
from reservations.services.holds import HoldService
from reservations.services.owner_block_requests import OwnerBlockRequestService

if TYPE_CHECKING:
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import Guest, TermsVersion

pytestmark = pytest.mark.django_db

FROM = date(2026, 7, 1)
TO = date(2026, 7, 8)


def _user() -> User:
    return cast(User, UserFactory())


def _booking(
    *,
    property: Property,
    guest: Guest,
    currency: Currency,
    terms: TermsVersion,
    date_from: date,
    date_to: date,
    status: str,
) -> Booking:
    quotation = Quotation.objects.create(
        guest=guest,
        currency=currency,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        currency=currency,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        status=status,
    )


def test_create_makes_pending_request(property_: Property) -> None:
    req = OwnerBlockRequestService.create(
        property=property_,
        requested_by=_user(),
        date_from=FROM,
        date_to=TO,
        kind=OwnerBlockKind.OWNER_STAY.value,
    )
    assert req.status == OwnerBlockRequestStatus.PENDING.value
    assert req.resulting_hold_id is None


def test_create_rejects_overlapping_booking(
    property_: Property, guest: Guest, gbp: Currency, terms: TermsVersion
) -> None:
    _booking(
        property=property_,
        guest=guest,
        currency=gbp,
        terms=terms,
        date_from=FROM,
        date_to=TO,
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    with pytest.raises(OverlappingBooking):
        OwnerBlockRequestService.create(
            property=property_,
            requested_by=_user(),
            date_from=date(2026, 7, 3),
            date_to=date(2026, 7, 10),
        )


def test_create_rejects_overlapping_live_hold(property_: Property) -> None:
    HoldService.place(
        property=property_,
        date_from=FROM,
        date_to=TO,
        reason=BookingHoldReason.OWNER_BLOCK.value,
        never_expires=True,
    )
    with pytest.raises(HoldUnavailable):
        OwnerBlockRequestService.create(
            property=property_,
            requested_by=_user(),
            date_from=date(2026, 7, 3),
            date_to=date(2026, 7, 10),
        )


def test_approve_places_indefinite_hold(property_: Property) -> None:
    req = OwnerBlockRequestService.create(
        property=property_,
        requested_by=_user(),
        date_from=FROM,
        date_to=TO,
        kind=OwnerBlockKind.OWNER_STAY.value,
    )
    reviewer = _user()
    OwnerBlockRequestService.approve(req, actor=reviewer)
    req.refresh_from_db()

    assert req.status == OwnerBlockRequestStatus.APPROVED.value
    assert req.reviewed_by_id == reviewer.id
    assert req.reviewed_at is not None
    hold = req.resulting_hold
    assert hold is not None
    assert hold.expires_at is None  # indefinite
    assert hold.reason == BookingHoldReason.OWNER_BLOCK.value
    assert hold.is_live() is True


def test_approve_maintenance_kind_maps_to_maintenance_reason(property_: Property) -> None:
    req = OwnerBlockRequestService.create(
        property=property_,
        requested_by=_user(),
        date_from=FROM,
        date_to=TO,
        kind=OwnerBlockKind.MAINTENANCE.value,
    )
    OwnerBlockRequestService.approve(req, actor=_user())
    req.refresh_from_db()
    assert req.resulting_hold is not None
    assert req.resulting_hold.reason == BookingHoldReason.MAINTENANCE.value


def test_approve_rejects_booking_landed_after_submit(
    property_: Property, guest: Guest, gbp: Currency, terms: TermsVersion
) -> None:
    """A booking that lands between submit and approve blocks approval."""
    req = OwnerBlockRequestService.create(
        property=property_,
        requested_by=_user(),
        date_from=FROM,
        date_to=TO,
    )
    _booking(
        property=property_,
        guest=guest,
        currency=gbp,
        terms=terms,
        date_from=FROM,
        date_to=TO,
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    with pytest.raises(OverlappingBooking):
        OwnerBlockRequestService.approve(req, actor=_user())
    req.refresh_from_db()
    assert req.status == OwnerBlockRequestStatus.PENDING.value


def test_approve_requires_pending(property_: Property) -> None:
    req = OwnerBlockRequestService.create(
        property=property_, requested_by=_user(), date_from=FROM, date_to=TO
    )
    OwnerBlockRequestService.decline(req, "no", actor=_user())
    with pytest.raises(InvalidTransition):
        OwnerBlockRequestService.approve(req, actor=_user())


def test_decline_sets_declined(property_: Property) -> None:
    req = OwnerBlockRequestService.create(
        property=property_, requested_by=_user(), date_from=FROM, date_to=TO
    )
    OwnerBlockRequestService.decline(req, "Owner double-booked", actor=_user())
    req.refresh_from_db()
    assert req.status == OwnerBlockRequestStatus.DECLINED.value
    assert req.review_note == "Owner double-booked"
    assert req.resulting_hold_id is None


def test_cancel_pending(property_: Property) -> None:
    req = OwnerBlockRequestService.create(
        property=property_, requested_by=_user(), date_from=FROM, date_to=TO
    )
    OwnerBlockRequestService.cancel(req, actor=_user())
    req.refresh_from_db()
    assert req.status == OwnerBlockRequestStatus.CANCELLED.value


def test_cancel_after_approve_releases_hold(property_: Property) -> None:
    req = OwnerBlockRequestService.create(
        property=property_, requested_by=_user(), date_from=FROM, date_to=TO
    )
    OwnerBlockRequestService.approve(req, actor=_user())
    req.refresh_from_db()
    hold_id = req.resulting_hold_id
    assert hold_id is not None

    OwnerBlockRequestService.cancel(req, actor=_user())
    req.refresh_from_db()
    assert req.status == OwnerBlockRequestStatus.CANCELLED.value
    hold = BookingHold.objects.get(pk=hold_id)
    assert hold.released_at is not None
    assert hold.is_live() is False
