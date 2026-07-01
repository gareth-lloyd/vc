"""GAP-033 Signal 1 — owner-block lifecycle touches `availability_owner_updated_at`.

`OwnerBlockService.create` and `.cancel` (the owner-availability changes) bump
the property's Signal 1 timestamp; everything that is *not* an owner-sourced
availability change leaves it untouched: staff `contest()`, iCal imports/cancels,
quotation holds, and booking conversions. Acceptance tested both ways.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, cast

import pytest
from django.utils import timezone

from accounts.factories import UserFactory
from accounts.models import User
from reservations.enums import (
    BookingHoldReason,
    BookingStatus,
    PaymentMethod,
)
from reservations.models import Booking, Quotation, QuotationLine
from reservations.services.holds import HoldService
from reservations.services.owner_block import OwnerBlockService

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import TermsVersion

pytestmark = pytest.mark.django_db

FROM = date(2026, 7, 1)
TO = date(2026, 7, 8)


def _user() -> User:
    return cast(User, UserFactory())


def _clear_owner_updated(property: Property) -> None:
    """Reset Signal 1 so a follow-up action's touch is observable in isolation."""
    property.availability_owner_updated_at = None
    property.save(update_fields=["availability_owner_updated_at"])


# --- touches (owner-sourced availability changes) ---------------------------


def test_manual_create_touches_owner_updated(property_: Property) -> None:
    assert property_.availability_owner_updated_at is None
    OwnerBlockService.create(property=property_, created_by=_user(), date_from=FROM, date_to=TO)
    property_.refresh_from_db()
    assert property_.availability_owner_updated_at is not None


def test_manual_cancel_touches_owner_updated(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    _clear_owner_updated(property_)

    OwnerBlockService.cancel(block, actor=_user())

    property_.refresh_from_db()
    assert property_.availability_owner_updated_at is not None


# --- non-touches (everything that is not an owner availability change) ------


def test_contest_does_not_touch_owner_updated(property_: Property) -> None:
    block = OwnerBlockService.create(
        property=property_, created_by=_user(), date_from=FROM, date_to=TO
    )
    _clear_owner_updated(property_)

    OwnerBlockService.contest(block, actor=_user(), reason="guest enquiry")

    property_.refresh_from_db()
    assert property_.availability_owner_updated_at is None


def test_imported_create_does_not_touch_owner_updated(property_: Property) -> None:
    OwnerBlockService.create_imported(
        property=property_,
        date_from=FROM,
        date_to=TO,
        idempotency_key="2026-07-01_2026-07-08",
    )
    property_.refresh_from_db()
    assert property_.availability_owner_updated_at is None


def test_imported_cancel_does_not_touch_owner_updated(property_: Property) -> None:
    block = OwnerBlockService.create_imported(
        property=property_,
        date_from=FROM,
        date_to=TO,
        idempotency_key="2026-07-01_2026-07-08",
    )
    # field is None after the import; cancelling an iCal block must keep it None
    OwnerBlockService.cancel(block, actor=None)
    property_.refresh_from_db()
    assert property_.availability_owner_updated_at is None


def test_quotation_hold_does_not_touch_owner_updated(
    property_: Property,
    customer: Person,
    terms: TermsVersion,
) -> None:
    quotation = Quotation.objects.create(
        enquiry=customer.enquiries_as_customer.create(),
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    HoldService.place(
        property=property_,
        date_from=FROM,
        date_to=TO,
        reason=BookingHoldReason.QUOTATION_OPEN.value,
        quotation=quotation,
    )
    property_.refresh_from_db()
    assert property_.availability_owner_updated_at is None


def test_booking_conversion_does_not_touch_owner_updated(
    property_: Property,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    quotation = Quotation.objects.create(
        enquiry=customer.enquiries_as_customer.create(),
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=FROM,
        date_to=TO,
        adults=2,
        total=Decimal("1400.00"),
    )
    Booking.objects.create(
        quotation_line=line,
        person=customer,
        property=property_,
        date_from=FROM,
        date_to=TO,
        adults=2,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    property_.refresh_from_db()
    assert property_.availability_owner_updated_at is None
