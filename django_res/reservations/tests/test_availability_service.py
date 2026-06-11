"""AvailabilityService — backed by live BookingHold + occupying Booking.

These exercise the read paths the calendar view depends on. Manual
blocks/holds/bookings must actually suppress availability (the service used
to be an inert stub).
"""

from __future__ import annotations

from datetime import date, time, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from core.tests import assert_max_queries
from reservations.enums import BookingHoldReason, BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    BookingHold,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)
from reservations.services import AvailabilityService

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
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property,
        currency=currency,
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
        cancelled_at=(timezone.now() if status == BookingStatus.CANCELLED.value else None),
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
# 5b. A resting DRAFT booking (legacy migration imports rest in DRAFT to
# bypass the overlap constraint) still occupies the range — it is real
# occupancy even though the DB write-constraint set omits DRAFT.
# ----------------------------------------------------------------------
def test_resting_draft_booking_occupies_range(
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
        date_from=date(2026, 8, 10),
        date_to=date(2026, 8, 17),
        status=BookingStatus.DRAFT.value,
    )
    assert (
        AvailabilityService.is_available(property_, date(2026, 8, 12), date(2026, 8, 14)) is False
    )
    conflicts = AvailabilityService.conflicts(property_, date(2026, 8, 10), date(2026, 8, 17))
    assert [c.kind for c in conflicts] == ["booked"]
    cal = AvailabilityService.calendar(property_, date(2026, 8, 9), date(2026, 8, 18))
    assert cal[date(2026, 8, 12)].reason == "booked"


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
    # Two availability queries (holds + bookings); the booking's lone checkout
    # day makes the service resolve the property's changeover times once more to
    # decide turnover (here: no PropertySettings row → one extra lookup). Still
    # flat in the number of holds/bookings/days.
    with assert_max_queries(3):
        cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 7, 30))
    assert cal[date(2026, 6, 6)].reason == "owner_block"
    assert cal[date(2026, 6, 13)].reason == "booked"
    assert cal[date(2026, 6, 22)].reason == "maintenance"


# ----------------------------------------------------------------------
# 9. Refined reason mapping + block_id (B1)
# ----------------------------------------------------------------------
def _quotation(guest: Guest, currency: Currency, terms: TermsVersion) -> Quotation:
    return Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


@pytest.mark.parametrize(
    ("reason", "expected_kind"),
    [
        (BookingHoldReason.OWNER_BLOCK.value, "owner_block"),
        (BookingHoldReason.MAINTENANCE.value, "maintenance"),
        (BookingHoldReason.MANUAL.value, "manual"),
    ],
)
def test_editable_block_carries_block_id(
    property_: Property, reason: str, expected_kind: str
) -> None:
    hold = _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=reason,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 9), date(2026, 6, 18))
    assert cal[date(2026, 6, 12)].reason == expected_kind
    assert cal[date(2026, 6, 12)].block_id == hold.pk


def test_quotation_hold_maps_to_quotation_reason_no_block_id(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    quotation = _quotation(guest, gbp, terms)
    BookingHold.objects.create(
        property=property_,
        quotation=quotation,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(days=5),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 9), date(2026, 6, 18))
    assert cal[date(2026, 6, 12)].reason == "quotation"
    assert cal[date(2026, 6, 12)].block_id is None
    # No edit affordance (block_id stays None) but a read-only link to the
    # owning quotation so the operator can click through from the calendar.
    assert cal[date(2026, 6, 12)].quotation_id == quotation.pk


def test_operator_block_has_no_quotation_id(property_: Property) -> None:
    _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        reason=BookingHoldReason.MANUAL.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 9), date(2026, 6, 18))
    assert cal[date(2026, 6, 12)].quotation_id is None


def test_booking_cell_has_no_block_id_and_booked_outranks_manual(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    _hold(
        property=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        reason=BookingHoldReason.MANUAL.value,
    )
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 7, 1), date(2026, 7, 8))
    assert cal[date(2026, 7, 3)].reason == "booked"
    assert cal[date(2026, 7, 3)].block_id is None


# ----------------------------------------------------------------------
# 10. Half-day changeover segments (B2)
# ----------------------------------------------------------------------
def _set_times(property_: Property, *, check_out: time, check_in: time) -> None:
    from properties.models import PropertySettings

    PropertySettings.objects.update_or_create(
        property=property_,
        defaults={"check_out_time": check_out, "check_in_time": check_in},
    )


def test_changeover_day_splits_am_pm(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    _set_times(property_, check_out=time(10, 0), check_in=time(16, 0))
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),  # departs morning of the 8th
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    _hold(
        property=property_,
        date_from=date(2026, 6, 8),  # arrives afternoon of the 8th
        date_to=date(2026, 6, 12),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 15))

    split = cal[date(2026, 6, 8)]
    assert split.segments is not None
    assert split.segments["am"].reason == "booked"
    assert split.segments["pm"].reason == "owner_block"
    assert split.available is False
    assert split.reason == "booked"  # rollup = higher priority of the two halves

    assert cal[date(2026, 6, 7)].segments is None
    assert cal[date(2026, 6, 7)].reason == "booked"
    assert cal[date(2026, 6, 9)].segments is None
    assert cal[date(2026, 6, 9)].reason == "owner_block"


def test_no_split_when_times_missing(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    _hold(
        property=property_,
        date_from=date(2026, 6, 8),
        date_to=date(2026, 6, 12),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 15))
    assert cal[date(2026, 6, 8)].segments is None
    assert cal[date(2026, 6, 8)].available is False
    assert cal[date(2026, 6, 8)].reason == "owner_block"


def test_no_split_when_checkout_after_checkin(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    _set_times(property_, check_out=time(16, 0), check_in=time(10, 0))
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    _hold(
        property=property_,
        date_from=date(2026, 6, 8),
        date_to=date(2026, 6, 12),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 15))
    assert cal[date(2026, 6, 8)].segments is None


def test_split_priority_booking_over_hold_same_side(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    _set_times(property_, check_out=time(10, 0), check_in=time(16, 0))
    # Two intervals depart on the 8th: a manual hold and a booking.
    _hold(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        reason=BookingHoldReason.MANUAL.value,
    )
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 2),
        date_to=date(2026, 6, 8),
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    _hold(
        property=property_,
        date_from=date(2026, 6, 8),
        date_to=date(2026, 6, 12),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 15))
    split = cal[date(2026, 6, 8)]
    assert split.segments is not None
    assert split.segments["am"].reason == "booked"
    assert split.segments["pm"].reason == "owner_block"


def test_calendar_query_count_with_split(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    _set_times(property_, check_out=time(10, 0), check_in=time(16, 0))
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    _hold(
        property=property_,
        date_from=date(2026, 6, 8),
        date_to=date(2026, 6, 12),
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    with assert_max_queries(4):
        cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 30))
    assert cal[date(2026, 6, 8)].segments is not None


# ----------------------------------------------------------------------
# 11. Lone booking checkout turnover (PR2) — bookings only, blocks stay whole
# ----------------------------------------------------------------------
def test_lone_booking_checkout_is_split_and_stays_available(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    """A booking's lone checkout day is sellable as a new arrival: AM booked,
    PM available, and the cell itself stays available."""
    _set_times(property_, check_out=time(10, 0), check_in=time(16, 0))
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),  # departs morning of the 8th, nobody arrives
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 15))

    checkout = cal[date(2026, 6, 8)]
    assert checkout.available is True
    assert checkout.segments is not None
    assert checkout.segments["am"].reason == "booked"
    assert checkout.segments["am"].available is False
    assert checkout.segments["pm"].available is True
    # The last full night is still wholly booked.
    assert cal[date(2026, 6, 7)].segments is None
    assert cal[date(2026, 6, 7)].available is False


def test_lone_booking_checkin_day_stays_whole(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    """The morning of a check-in is not sellable as a night, so no half-bar."""
    _set_times(property_, check_out=time(10, 0), check_in=time(16, 0))
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 14),
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 20))
    assert cal[date(2026, 6, 10)].segments is None
    assert cal[date(2026, 6, 10)].available is False
    assert cal[date(2026, 6, 10)].reason == "booked"


@pytest.mark.parametrize(
    "reason",
    [
        BookingHoldReason.OWNER_BLOCK.value,
        BookingHoldReason.MAINTENANCE.value,
        BookingHoldReason.MANUAL.value,
    ],
)
def test_block_checkout_day_stays_whole_no_turnover(property_: Property, reason: str) -> None:
    """Blocks have no checkout to turn over: the exclusive `date_to` is simply
    available, whole-day, never a half-bar — for every block reason."""
    _set_times(property_, check_out=time(10, 0), check_in=time(16, 0))
    _hold(
        property=property_,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        reason=reason,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 15))
    assert cal[date(2026, 6, 8)].available is True
    assert cal[date(2026, 6, 8)].segments is None


def test_lone_checkout_not_split_without_changeover_times(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    """No property changeover times → the checkout day is whole-day available."""
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 15))
    assert cal[date(2026, 6, 8)].available is True
    assert cal[date(2026, 6, 8)].segments is None


def test_calendar_query_count_with_lone_checkout(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    _set_times(property_, check_out=time(10, 0), check_in=time(16, 0))
    _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 8),
        status=BookingStatus.DEPOSIT_PAID.value,
    )
    with assert_max_queries(4):
        cal = AvailabilityService.calendar(property_, date(2026, 6, 1), date(2026, 6, 30))
    assert cal[date(2026, 6, 8)].segments is not None


# ----------------------------------------------------------------------
# 12. multi() — cross-property range bands for the combined timeline
# ----------------------------------------------------------------------
@pytest.fixture
def other_property(property_: Property) -> Property:
    from properties.models import Property as PropertyModel

    return PropertyModel.objects.create(
        name="Other Villa",
        display_name="Other Villa",
        slug="other-villa",
        category=property_.category,
        group=property_.group,
        region=property_.region,
    )


def test_multi_returns_live_holds_and_occupying_bookings(
    property_: Property,
    other_property: Property,
    gbp: Currency,
    guest: Guest,
    terms: TermsVersion,
) -> None:
    hold = _hold(property=property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17))
    booking = _make_booking(
        property=other_property,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 20),
        date_to=date(2026, 6, 27),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    holds, bookings = AvailabilityService.multi(
        [property_.pk, other_property.pk], date(2026, 6, 1), date(2026, 7, 1)
    )
    assert [h.pk for h in holds] == [hold.pk]
    assert [b.pk for b in bookings] == [booking.pk]


def test_multi_includes_resting_draft_booking(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    booking = _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 8, 10),
        date_to=date(2026, 8, 17),
        status=BookingStatus.DRAFT.value,
    )
    _, bookings = AvailabilityService.multi([property_.pk], date(2026, 8, 1), date(2026, 9, 1))
    assert [b.pk for b in bookings] == [booking.pk]


@pytest.mark.parametrize(
    "status",
    [BookingStatus.CANCELLED.value, BookingStatus.CHECKED_OUT.value],
)
def test_multi_excludes_terminal_bookings(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion, status: str
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
    _, bookings = AvailabilityService.multi([property_.pk], date(2026, 7, 1), date(2026, 8, 1))
    assert list(bookings) == []


def test_multi_excludes_released_and_expired_holds(property_: Property) -> None:
    _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        released=True,
    )
    _hold(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expired=True,
    )
    holds, _ = AvailabilityService.multi([property_.pk], date(2026, 6, 1), date(2026, 7, 1))
    assert list(holds) == []


def test_multi_includes_null_expiry_hold(property_: Property) -> None:
    hold = BookingHold.objects.create(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=None,
        reason=BookingHoldReason.OWNER_BLOCK.value,
    )
    holds, _ = AvailabilityService.multi([property_.pk], date(2026, 6, 1), date(2026, 7, 1))
    assert [h.pk for h in holds] == [hold.pk]


def test_multi_excludes_booking_linked_holds(
    property_: Property, gbp: Currency, guest: Guest, terms: TermsVersion
) -> None:
    """A deposit-pending booking has both a live hold and an occupying booking
    row — the hold is excluded so the timeline paints one band per stay."""
    booking = _make_booking(
        property=property_,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    BookingHold.objects.create(
        property=property_,
        booking=booking,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        expires_at=timezone.now() + timedelta(days=30),
        reason=BookingHoldReason.QUOTATION_OPEN.value,
    )
    holds, bookings = AvailabilityService.multi([property_.pk], date(2026, 6, 1), date(2026, 7, 1))
    assert list(holds) == []
    assert [b.pk for b in bookings] == [booking.pk]


def test_multi_scopes_to_ids_and_window(
    property_: Property,
    other_property: Property,
    gbp: Currency,
    guest: Guest,
    terms: TermsVersion,
) -> None:
    # Other property's rows must not appear when only `property_` is asked for.
    _hold(property=other_property, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17))
    _make_booking(
        property=other_property,
        currency=gbp,
        guest=guest,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        status=BookingStatus.AWAITING_DEPOSIT.value,
    )
    # Out-of-window rows on the requested property must not appear either.
    _hold(property=property_, date_from=date(2026, 9, 1), date_to=date(2026, 9, 8))
    holds, bookings = AvailabilityService.multi([property_.pk], date(2026, 6, 1), date(2026, 7, 1))
    assert list(holds) == []
    assert list(bookings) == []


def test_multi_includes_band_overhanging_window(property_: Property) -> None:
    hold = _hold(property=property_, date_from=date(2026, 5, 20), date_to=date(2026, 7, 10))
    holds, _ = AvailabilityService.multi([property_.pk], date(2026, 6, 1), date(2026, 7, 1))
    assert [h.pk for h in holds] == [hold.pk]
