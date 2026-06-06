"""Tests for OwnerBlockService: created-approved lifecycle + overlap guards."""

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
    OwnerBlockStatus,
    PaymentMethod,
)
from reservations.models import Booking, BookingHold, Quotation, QuotationLine
from reservations.services.holds import HoldService
from reservations.services.owner_block import OwnerBlockService

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


def test_create_makes_approved_block_with_indefinite_hold(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_,
        created_by=_user(),
        date_from=FROM,
        date_to=TO,
        kind=OwnerBlockKind.OWNER_STAY.value,
    )
    assert block.status == OwnerBlockStatus.APPROVED.value
    hold = block.resulting_hold
    assert hold is not None
    assert hold.expires_at is None  # indefinite
    assert hold.reason == BookingHoldReason.OWNER_BLOCK.value
    assert hold.is_live() is True


def test_create_maintenance_kind_maps_to_maintenance_reason(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_,
        created_by=_user(),
        date_from=FROM,
        date_to=TO,
        kind=OwnerBlockKind.MAINTENANCE.value,
    )
    assert block.resulting_hold is not None
    assert block.resulting_hold.reason == BookingHoldReason.MAINTENANCE.value


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
        OwnerBlockService.create(
            property=property_,
            created_by=_user(),
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
        OwnerBlockService.create(
            property=property_,
            created_by=_user(),
            date_from=date(2026, 7, 3),
            date_to=date(2026, 7, 10),
        )


def test_cancel_releases_hold(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    hold_id = block.resulting_hold_id
    assert hold_id is not None

    OwnerBlockService.cancel(block, actor=_user())
    block.refresh_from_db()
    assert block.status == OwnerBlockStatus.CANCELLED.value
    hold = BookingHold.objects.get(pk=hold_id)
    assert hold.released_at is not None
    assert hold.is_live() is False


def test_cancel_rejects_already_cancelled(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    OwnerBlockService.cancel(block, actor=_user())
    with pytest.raises(InvalidTransition):
        OwnerBlockService.cancel(block, actor=_user())
