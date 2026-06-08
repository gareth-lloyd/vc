"""Tests for the Booking state machine + non-transition mutations."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from core.exceptions import InvalidTransition, NoRateAvailable, OverlappingBooking
from pricing.models import Currency, RateRule
from properties.models import Property
from reservations.enums import BookingStatus, PaymentMethod
from reservations.models import (
    Booking,
    BookingEvent,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)


@pytest.fixture
def quotation_line(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> QuotationLine:
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )


@pytest.fixture
def booking(
    quotation_line: QuotationLine,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    return Booking.objects.create(
        quotation_line=quotation_line,
        guest=guest,
        property=property_,
        date_from=quotation_line.date_from,
        date_to=quotation_line.date_to,
        adults=quotation_line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )


# ---------------------------------------------------------------------------
# Transition table — bulk parametrised across the 06-availability.md table
# ---------------------------------------------------------------------------


def _set_status(booking: Booking, status: str) -> Booking:
    booking.status = status
    booking.save(update_fields=["status", "updated_at"])
    return booking


_TRANSITION_TABLE: list[tuple[str, str, str, tuple[str, ...]]] = [
    # (method, from_status, to_status, kwargs-as-string of disallowed-source states)
    (
        "submit",
        BookingStatus.DRAFT.value,
        BookingStatus.PENDING_OWNER_APPROVAL.value,
        (BookingStatus.AWAITING_DEPOSIT.value, BookingStatus.CHECKED_OUT.value),
    ),
    (
        "auto_accept",
        BookingStatus.DRAFT.value,
        BookingStatus.AWAITING_DEPOSIT.value,
        (BookingStatus.PENDING_OWNER_APPROVAL.value, BookingStatus.CANCELLED.value),
    ),
    (
        "owner_approve",
        BookingStatus.PENDING_OWNER_APPROVAL.value,
        BookingStatus.AWAITING_DEPOSIT.value,
        (BookingStatus.DRAFT.value, BookingStatus.AWAITING_DEPOSIT.value),
    ),
    (
        "record_deposit",
        BookingStatus.AWAITING_DEPOSIT.value,
        BookingStatus.DEPOSIT_PAID.value,
        (BookingStatus.DRAFT.value, BookingStatus.BALANCE_PAID.value),
    ),
    (
        "arm_balance",
        BookingStatus.DEPOSIT_PAID.value,
        BookingStatus.AWAITING_BALANCE.value,
        (BookingStatus.AWAITING_DEPOSIT.value, BookingStatus.CHECKED_IN.value),
    ),
    (
        "check_in",
        BookingStatus.BALANCE_PAID.value,
        BookingStatus.CHECKED_IN.value,
        (BookingStatus.AWAITING_BALANCE.value, BookingStatus.CHECKED_OUT.value),
    ),
    (
        "check_out",
        BookingStatus.CHECKED_IN.value,
        BookingStatus.CHECKED_OUT.value,
        (BookingStatus.BALANCE_PAID.value, BookingStatus.DRAFT.value),
    ),
    (
        "expire",
        BookingStatus.AWAITING_DEPOSIT.value,
        BookingStatus.EXPIRED.value,
        (BookingStatus.DRAFT.value, BookingStatus.DEPOSIT_PAID.value),
    ),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "from_status", "to_status", "_disallowed"), _TRANSITION_TABLE)
def test_transition_happy_path(
    booking: Booking,
    method: str,
    from_status: str,
    to_status: str,
    _disallowed: tuple[str, ...],
) -> None:
    _set_status(booking, from_status)
    bound = getattr(booking, method)
    if method == "owner_decline":
        bound("reason")
    else:
        bound()
    booking.refresh_from_db()
    assert booking.status == to_status
    assert BookingEvent.objects.filter(
        booking=booking, from_status=from_status, to_status=to_status
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(("method", "from_status", "_to", "disallowed"), _TRANSITION_TABLE)
def test_transition_from_disallowed_raises(
    booking: Booking,
    method: str,
    from_status: str,
    _to: str,
    disallowed: tuple[str, ...],
) -> None:
    bad = disallowed[0]
    _set_status(booking, bad)
    bound = getattr(booking, method)
    with pytest.raises(InvalidTransition):
        if method == "owner_decline":
            bound("reason")
        else:
            bound()


@pytest.mark.django_db
def test_owner_decline_happy_and_disallowed(booking: Booking) -> None:
    _set_status(booking, BookingStatus.PENDING_OWNER_APPROVAL.value)
    booking.owner_decline("rejected")
    booking.refresh_from_db()
    assert booking.status == BookingStatus.DECLINED.value

    # From DRAFT it should raise.
    other = _set_status(booking, BookingStatus.DRAFT.value)
    with pytest.raises(InvalidTransition):
        other.owner_decline("nope")


@pytest.mark.django_db
def test_record_balance_from_awaiting_balance(booking: Booking) -> None:
    _set_status(booking, BookingStatus.AWAITING_BALANCE.value)
    booking.record_balance()
    booking.refresh_from_db()
    assert booking.status == BookingStatus.BALANCE_PAID.value


@pytest.mark.django_db
def test_record_balance_from_deposit_paid(booking: Booking) -> None:
    _set_status(booking, BookingStatus.DEPOSIT_PAID.value)
    booking.record_balance()
    booking.refresh_from_db()
    assert booking.status == BookingStatus.BALANCE_PAID.value


@pytest.mark.django_db
@pytest.mark.parametrize(
    "starting",
    [
        BookingStatus.DRAFT.value,
        BookingStatus.PENDING_OWNER_APPROVAL.value,
        BookingStatus.AWAITING_DEPOSIT.value,
        BookingStatus.DEPOSIT_PAID.value,
        BookingStatus.AWAITING_BALANCE.value,
        BookingStatus.BALANCE_PAID.value,
        BookingStatus.CHECKED_IN.value,
    ],
)
def test_cancel_from_each_non_terminal_state(booking: Booking, starting: str) -> None:
    _set_status(booking, starting)
    booking.cancel("user requested")
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CANCELLED.value
    assert booking.cancelled_at is not None


@pytest.mark.django_db
def test_cancel_from_terminal_raises(booking: Booking) -> None:
    _set_status(booking, BookingStatus.CHECKED_OUT.value)
    with pytest.raises(InvalidTransition):
        booking.cancel("too late")


# ---------------------------------------------------------------------------
# modify_dates / modify_guests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_modify_dates_rerun_pricing_and_writes_event(booking: Booking, rate_rule: RateRule) -> None:
    _set_status(booking, BookingStatus.AWAITING_DEPOSIT.value)
    booking.modify_dates(date(2026, 7, 1), date(2026, 7, 8))
    booking.refresh_from_db()
    assert booking.date_from == date(2026, 7, 1)
    assert booking.date_to == date(2026, 7, 8)
    assert booking.pricing_snapshot
    assert booking.pricing_snapshot.get("rate_subtotal")
    # Same-state event.
    event = BookingEvent.objects.filter(booking=booking).latest("created_at")
    assert event.from_status == event.to_status == BookingStatus.AWAITING_DEPOSIT.value
    assert event.meta["from"] == [
        date(2026, 6, 10).isoformat(),
        date(2026, 6, 17).isoformat(),
    ]
    assert event.meta["to"] == [
        date(2026, 7, 1).isoformat(),
        date(2026, 7, 8).isoformat(),
    ]


@pytest.mark.django_db
def test_modify_dates_into_unrated_future_year_rejects_projection(
    booking: Booking, rate_rule: RateRule
) -> None:
    """A booking is a contract: modifying into a year with no confirmed rates must
    raise NoRateAvailable, not silently re-price onto a projected guide rate."""
    _set_status(booking, BookingStatus.AWAITING_DEPOSIT.value)
    with pytest.raises(NoRateAvailable):
        booking.modify_dates(date(2028, 7, 4), date(2028, 7, 11))
    booking.refresh_from_db()
    # Original dates and price stand — nothing was overwritten with a guide.
    assert booking.date_from == date(2026, 6, 10)
    assert booking.date_to == date(2026, 6, 17)
    assert booking.balance_due == Decimal("1400.00")


@pytest.mark.django_db
def test_modify_dates_from_terminal_raises(booking: Booking, rate_rule: RateRule) -> None:
    _set_status(booking, BookingStatus.CHECKED_OUT.value)
    with pytest.raises(InvalidTransition):
        booking.modify_dates(date(2026, 7, 1), date(2026, 7, 8))


@pytest.mark.django_db
def test_modify_guests_rerun_pricing_and_writes_event(
    booking: Booking, rate_rule: RateRule
) -> None:
    _set_status(booking, BookingStatus.AWAITING_DEPOSIT.value)
    booking.modify_guests(adults=4, children=1)
    booking.refresh_from_db()
    assert booking.adults == 4
    assert booking.children == 1
    event = BookingEvent.objects.filter(booking=booking).latest("created_at")
    assert event.from_status == event.to_status == BookingStatus.AWAITING_DEPOSIT.value
    assert event.meta["from"] == {"adults": 2, "children": 0}
    assert event.meta["to"] == {"adults": 4, "children": 1}


@pytest.mark.django_db
def test_modify_guests_from_checked_in_raises(booking: Booking, rate_rule: RateRule) -> None:
    _set_status(booking, BookingStatus.CHECKED_IN.value)
    with pytest.raises(InvalidTransition):
        booking.modify_guests(adults=4, children=0)


# ---------------------------------------------------------------------------
# archive / restore
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_archive_only_from_terminal(booking: Booking) -> None:
    _set_status(booking, BookingStatus.CHECKED_OUT.value)
    booking.archive()
    booking.refresh_from_db()
    assert booking.is_archived is True
    assert booking.archived_at is not None


@pytest.mark.django_db
def test_archive_from_active_raises(booking: Booking) -> None:
    _set_status(booking, BookingStatus.AWAITING_DEPOSIT.value)
    with pytest.raises(InvalidTransition):
        booking.archive()


@pytest.mark.django_db
def test_restore_reverses_archive(booking: Booking) -> None:
    booking.cancel("test reason")  # CANCELLED is terminal + sets cancelled_at
    booking.archive()
    booking.restore()
    booking.refresh_from_db()
    assert booking.is_archived is False
    assert booking.archived_at is None


# ---------------------------------------------------------------------------
# Signal fan-out
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_booking_transitioned_signal_fires(booking: Booking) -> None:
    from reservations.signals import booking_transitioned

    seen: list[dict[str, Any]] = []

    def _handler(sender: type, **kwargs: Any) -> None:
        seen.append(kwargs)

    booking_transitioned.connect(_handler, sender=Booking, dispatch_uid="test-booking-signal")
    try:
        _set_status(booking, BookingStatus.DRAFT.value)
        booking.submit()
    finally:
        booking_transitioned.disconnect(sender=Booking, dispatch_uid="test-booking-signal")

    assert len(seen) == 1
    assert seen[0]["from_status"] == BookingStatus.DRAFT.value
    assert seen[0]["to_status"] == BookingStatus.PENDING_OWNER_APPROVAL.value


@pytest.mark.django_db
def test_reference_auto_generated(booking: Booking) -> None:
    assert booking.reference.startswith("VC")


# ---------------------------------------------------------------------------
# CheckConstraint invariants
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cancelled_at_requires_cancelled_status(booking: Booking) -> None:
    with pytest.raises(Exception, match="booking_cancelled_at_implies_cancelled_status"):
        Booking.objects.filter(pk=booking.pk).update(
            cancelled_at=timezone.now(),
            status=BookingStatus.DRAFT.value,
        )


@pytest.mark.django_db
def test_cancelled_at_allowed_when_status_cancelled(booking: Booking) -> None:
    Booking.objects.filter(pk=booking.pk).update(
        cancelled_at=timezone.now(),
        status=BookingStatus.CANCELLED.value,
    )
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CANCELLED.value
    assert booking.cancelled_at is not None


@pytest.mark.django_db
def test_cancelled_status_requires_cancelled_at(booking: Booking) -> None:
    """Inverse of the above: a CANCELLED booking must carry a cancelled_at."""
    with pytest.raises(Exception, match="booking_cancelled_status_requires_cancelled_at"):
        Booking.objects.filter(pk=booking.pk).update(
            status=BookingStatus.CANCELLED.value,
            cancelled_at=None,
        )


@pytest.mark.django_db
def test_archived_at_requires_terminal_status(booking: Booking) -> None:
    with pytest.raises(Exception, match="booking_archived_at_requires_terminal_status"):
        Booking.objects.filter(pk=booking.pk).update(
            archived_at=timezone.now(),
            status=BookingStatus.DRAFT.value,
        )


@pytest.mark.django_db
def test_archived_at_allowed_on_terminal_status(booking: Booking) -> None:
    Booking.objects.filter(pk=booking.pk).update(
        archived_at=timezone.now(),
        status=BookingStatus.CHECKED_OUT.value,
    )
    booking.refresh_from_db()
    assert booking.archived_at is not None


@pytest.mark.django_db
def test_cancel_transition_satisfies_constraint(booking: Booking) -> None:
    booking.cancel("test reason")
    booking.refresh_from_db()
    assert booking.status == BookingStatus.CANCELLED.value
    assert booking.cancelled_at is not None


@pytest.mark.django_db
def test_archive_transition_satisfies_constraint(booking: Booking) -> None:
    booking.cancel("test reason")
    booking.archive()
    booking.refresh_from_db()
    assert booking.archived_at is not None


# ---------------------------------------------------------------------------
# Date-range overlap: no two non-terminal bookings can hold the same dates.
#
# Drafts and pending-owner-approval bookings are *both* blocked by the
# exclusion constraint — the historical bug was that pending-approval
# overlaps were silently permitted, then exploded as IntegrityError when
# the first owner approved. We surface them as `OverlappingBooking` at the
# moment the conflict arises.
# ---------------------------------------------------------------------------


def _second_quotation_line(
    *,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    date_from: date,
    date_to: date,
) -> QuotationLine:
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(),
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        total=Decimal("1400.00"),
    )


def _second_booking(
    *,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    date_from: date,
    date_to: date,
) -> Booking:
    line = _second_quotation_line(
        guest=guest,
        gbp=gbp,
        terms=terms,
        property_=property_,
        date_from=date_from,
        date_to=date_to,
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property_,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )


@pytest.mark.django_db
def test_two_pending_approvals_cannot_overlap(
    booking: Booking,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """B4: two parallel submit_for_approval calls for overlapping dates."""
    _set_status(booking, BookingStatus.DRAFT.value)
    booking.submit()

    second = _second_booking(
        guest=guest,
        gbp=gbp,
        terms=terms,
        property_=property_,
        # overlaps booking (2026-06-10..06-17)
        date_from=date(2026, 6, 14),
        date_to=date(2026, 6, 20),
    )
    with pytest.raises(OverlappingBooking):
        second.submit()

    second.refresh_from_db()
    assert second.status == BookingStatus.DRAFT.value


@pytest.mark.django_db
def test_auto_accept_into_overlap_raises_overlapping_booking(
    booking: Booking,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """A draft on overlapping dates can't auto-accept while another booking
    already occupies the range — surface as domain error rather than IntegrityError."""
    _set_status(booking, BookingStatus.AWAITING_DEPOSIT.value)

    second = _second_booking(
        guest=guest,
        gbp=gbp,
        terms=terms,
        property_=property_,
        date_from=date(2026, 6, 14),
        date_to=date(2026, 6, 20),
    )
    assert second.status == BookingStatus.DRAFT.value

    with pytest.raises(OverlappingBooking):
        second.auto_accept()

    second.refresh_from_db()
    assert second.status == BookingStatus.DRAFT.value


@pytest.mark.django_db
def test_drafts_can_overlap(
    booking: Booking,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """DRAFT is pre-commitment; two drafts on the same dates is fine."""
    _set_status(booking, BookingStatus.DRAFT.value)
    second = _second_booking(
        guest=guest,
        gbp=gbp,
        terms=terms,
        property_=property_,
        date_from=date(2026, 6, 14),
        date_to=date(2026, 6, 20),
    )
    assert second.status == BookingStatus.DRAFT.value


@pytest.mark.django_db
def test_non_overlapping_pending_approvals_coexist(
    booking: Booking,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """Sanity check: non-overlapping pending bookings still work."""
    _set_status(booking, BookingStatus.DRAFT.value)
    booking.submit()

    second = _second_booking(
        guest=guest,
        gbp=gbp,
        terms=terms,
        property_=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
    )
    second.submit()

    second.refresh_from_db()
    assert second.status == BookingStatus.PENDING_OWNER_APPROVAL.value


@pytest.mark.django_db
def test_modify_dates_into_overlap_raises_overlapping_booking(
    booking: Booking,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
    rate_rule: RateRule,
) -> None:
    """modify_dates onto another booking's range must surface as OverlappingBooking,
    not raw IntegrityError, and must leave the in-memory booking unchanged."""
    _set_status(booking, BookingStatus.AWAITING_DEPOSIT.value)

    second = _second_booking(
        guest=guest,
        gbp=gbp,
        terms=terms,
        property_=property_,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 8),
    )
    _set_status(second, BookingStatus.AWAITING_DEPOSIT.value)

    with pytest.raises(OverlappingBooking):
        second.modify_dates(date(2026, 6, 14), date(2026, 6, 20))

    # In-memory state restored.
    assert second.date_from == date(2026, 7, 1)
    assert second.date_to == date(2026, 7, 8)

    # DB row unchanged.
    second.refresh_from_db()
    assert second.date_from == date(2026, 7, 1)
    assert second.date_to == date(2026, 7, 8)


# ---------------------------------------------------------------------------
# FG-006 — modify must lock + reload committed state before re-pricing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_modify_dates_reloads_committed_state_before_repricing(
    booking: Booking, rate_rule: RateRule
) -> None:
    """`modify_dates` must re-read the row under a lock before re-pricing.

    Simulates the lost-update window single-threaded: a stale handle (`stale`)
    is loaded, then another writer commits new dates through a second handle.
    When `stale.modify_dates(...)` runs, `_lock_for_update` re-fetches the row
    under `SELECT … FOR UPDATE`, so the event's `from` reflects the *committed*
    dates — not the stale ones the handle was loaded with. Without the lock
    helper the method would operate on the stale instance and record the wrong
    `from`, clobbering the other writer's change.
    """
    _set_status(booking, BookingStatus.AWAITING_DEPOSIT.value)

    # A handle loaded before a concurrent writer commits — its in-memory
    # date_from/date_to are now stale.
    stale = Booking.objects.get(pk=booking.pk)

    # Another writer moves the dates and commits.
    Booking.objects.get(pk=booking.pk).modify_dates(date(2026, 7, 1), date(2026, 7, 8))

    # The stale handle now modifies dates; the lock + reload must make it see
    # the committed July dates as its starting point, not the original June ones.
    stale.modify_dates(date(2026, 8, 1), date(2026, 8, 8))

    latest = BookingEvent.objects.filter(booking=booking).latest("created_at", "id")
    assert latest.meta["from"] == [date(2026, 7, 1).isoformat(), date(2026, 7, 8).isoformat()]
    assert latest.meta["to"] == [date(2026, 8, 1).isoformat(), date(2026, 8, 8).isoformat()]

    booking.refresh_from_db()
    assert booking.date_from == date(2026, 8, 1)
    assert booking.date_to == date(2026, 8, 8)


@pytest.mark.django_db
def test_modify_guests_reloads_committed_state_before_repricing(
    booking: Booking, rate_rule: RateRule
) -> None:
    """`modify_guests` takes the same lock + reload (FG-006)."""
    _set_status(booking, BookingStatus.AWAITING_DEPOSIT.value)

    stale = Booking.objects.get(pk=booking.pk)
    Booking.objects.get(pk=booking.pk).modify_guests(adults=3, children=0)

    stale.modify_guests(adults=5, children=1)

    latest = BookingEvent.objects.filter(booking=booking).latest("created_at", "id")
    assert latest.meta["from"] == {"adults": 3, "children": 0}
    assert latest.meta["to"] == {"adults": 5, "children": 1}


@pytest.mark.django_db
def test_lock_for_update_locks_and_reloads_in_one_query(booking: Booking) -> None:
    """The lock + reload is a single `SELECT … FOR UPDATE` round-trip.

    `_lock_for_update` must not take the lock with one query and then refresh
    the in-memory fields with a second, unlocked read — the locking select
    already returns the fresh row.
    """
    from core.tests import assert_max_queries

    # `django_db` runs the test inside an atomic block, so `select_for_update`
    # is permitted without an explicit `transaction.atomic()` (which would add
    # SAVEPOINT statements to the captured query count).
    with assert_max_queries(1):
        booking._lock_for_update()
