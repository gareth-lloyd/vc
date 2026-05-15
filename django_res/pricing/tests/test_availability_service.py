"""AvailabilityService — backed by live BookingHold + non-terminal Booking.

These exercise the read paths that the calendar view and the pricing
engine depend on. Manual blocks/holds/bookings must actually suppress
availability (the service used to be an inert stub).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from core.tests import assert_max_queries
from pricing.services import AvailabilityService
from reservations.enums import BookingHoldReason, BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    BookingHold,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)

if TYPE_CHECKING:
    from pricing.models import Currency
    from properties.models import Property

pytestmark = pytest.mark.django_db


# ----------------------------------------------------------------------
# Local fixtures (pricing conftest has no guest/terms graph)
# ----------------------------------------------------------------------
@pytest.fixture
def terms() -> TermsVersion:
    return TermsVersion.objects.create(
        version="2026-01",
        body_markdown="**T&Cs**",
        published_at=timezone.now(),
        is_current=True,
    )


@pytest.fixture
def guest() -> Guest:
    return Guest.objects.create(first_name="Ada", last_name="Lovelace", email="ada@example.com")


def _make_booking(
    *,
    property: Property,
    currency: Currency,
    guest: Guest,
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


def _hold(
    *,
    property: Property,
    date_from: date,
    date_to: date,
    reason: str = BookingHoldReason.OWNER_BLOCK.value,
    released: bool = False,
    expired: bool = False,
) -> BookingHold:
    now = timezone.now()
    return BookingHold.objects.create(
        property=property,
        date_from=date_from,
        date_to=date_to,
        expires_at=now - timedelta(days=1) if expired else now + timedelta(days=30),
        released_at=now if released else None,
        reason=reason,
    )


# ----------------------------------------------------------------------
# 1. Baseline
# ----------------------------------------------------------------------
def test_empty_property_is_fully_available(property_: Property) -> None:
    d0 = date(2026, 6, 1)
    assert AvailabilityService.is_available(property_, d0, d0 + timedelta(days=5)) is True
    assert AvailabilityService.conflicts(property_, d0, d0 + timedelta(days=5)) == []
    cal = AvailabilityService.calendar(property_, d0, d0 + timedelta(days=4))
    assert all(cell.available for cell in cal.values())


# ----------------------------------------------------------------------
# 2. Live owner block suppresses availability
# ----------------------------------------------------------------------
def test_live_owner_block_blocks_range(property_: Property) -> None:
    _hold(property=property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17))

    available = AvailabilityService.is_available(property_, date(2026, 6, 12), date(2026, 6, 14))
    assert available is False

    conflicts = AvailabilityService.conflicts(property_, date(2026, 6, 1), date(2026, 6, 30))
    assert len(conflicts) == 1
    assert conflicts[0].kind == "owner_block"

    cal = AvailabilityService.calendar(property_, date(2026, 6, 9), date(2026, 6, 18))
    assert cal[date(2026, 6, 9)].available is True
    assert cal[date(2026, 6, 12)].available is False
    assert cal[date(2026, 6, 12)].reason == "owner_block"


# ----------------------------------------------------------------------
# 3 + 4. Released / expired holds are ignored
# ----------------------------------------------------------------------
def test_released_hold_is_ignored(property_: Property) -> None:
    _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        released=True,
    )
    assert AvailabilityService.is_available(property_, date(2026, 6, 11), date(2026, 6, 15)) is True


def test_expired_hold_is_ignored(property_: Property) -> None:
    _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expired=True,
    )
    assert AvailabilityService.is_available(property_, date(2026, 6, 11), date(2026, 6, 15)) is True


# ----------------------------------------------------------------------
# 5. A non-terminal Booking blocks even with no covering hold
# ----------------------------------------------------------------------
def test_non_terminal_booking_blocks_without_hold(
    property_: Property,
    gbp: Currency,
    guest: Guest,
    terms: TermsVersion,
) -> None:
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    assert AvailabilityService.is_available(property_, date(2026, 7, 3), date(2026, 7, 5)) is False
    conflicts = AvailabilityService.conflicts(property_, date(2026, 7, 1), date(2026, 7, 8))
    assert [c.kind for c in conflicts] == ["booked"]


# ----------------------------------------------------------------------
# 6. Terminal bookings are ignored
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "status",
    [BookingStatus.CANCELLED.value, BookingStatus.CHECKED_OUT.value],
)
def test_terminal_booking_is_ignored(
    property_: Property,
    gbp: Currency,
    guest: Guest,
    terms: TermsVersion,
    status: str,
) -> None:
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        status=status,
    )
    assert AvailabilityService.is_available(property_, date(2026, 7, 3), date(2026, 7, 5)) is True


# ----------------------------------------------------------------------
# 7. ignore_hold_ids excludes the named hold (re-quote path)
# ----------------------------------------------------------------------
def test_ignore_hold_ids_excludes_own_hold(property_: Property) -> None:
    hold = _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=BookingHoldReason.MANUAL.value,
    )
    assert (
        AvailabilityService.is_available(
            property_,
            date(2026, 6, 11),
            date(2026, 6, 15),
            ignore_hold_ids=[hold.pk],
        )
        is True
    )


# ----------------------------------------------------------------------
# 8. calendar() is constant-query over a wide window
# ----------------------------------------------------------------------
def test_calendar_query_count_is_constant(
    property_: Property,
    gbp: Currency,
    guest: Guest,
    terms: TermsVersion,
) -> None:
    _hold(property=property_, date_from=date(2026, 6, 5), date_to=date(2026, 6, 9))
    _hold(
        property=property_,
        date_from=date(2026, 6, 20),
        date_to=date(2026, 6, 25),
        reason=BookingHoldReason.MAINTENANCE.value,
    )
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 12),
        date_to=date(2026, 6, 15),
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    with assert_max_queries(2):
        cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 7, 30))
    assert cal[date(2026, 6, 6)].reason == "owner_block"
    assert cal[date(2026, 6, 13)].reason == "booked"
    assert cal[date(2026, 6, 22)].reason == "maintenance"
