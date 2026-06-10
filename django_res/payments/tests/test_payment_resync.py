"""Tests for `PaymentScheduler.resync_for_booking` — schedule resize on
charge-item changes (legacy regenerated the schedule on every modify).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from payments.enums import PaymentPurpose, PaymentStatus
from payments.models import Payment
from payments.services import PaymentScheduler
from properties.models import Property
from properties.models.finance import GroupFinance, PropertyFinance
from reservations.models import Booking, BookingChargeItem, BookingEvent


def _ensure_finance(property_: Property) -> GroupFinance:
    gf, _ = GroupFinance.objects.get_or_create(group=property_.group)
    PropertyFinance.objects.get_or_create(property=property_)
    return gf


@pytest.fixture
def scheduled_booking(booking: Any, property_: Property) -> Booking:
    """Booking with the default 30% deposit / balance schedule in PENDING."""
    _ensure_finance(property_)
    fresh = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.create_for_booking(fresh)
    return fresh


def _row(booking: Booking, purpose: PaymentPurpose) -> Payment:
    return Payment.objects.get(booking=booking, purpose=purpose.value)


def _add_charge(booking: Booking, amount: str, label: str = "Extra") -> BookingChargeItem:
    return BookingChargeItem.objects.create(
        booking=booking, label=label, amount=Decimal(amount), currency=booking.currency
    )


@pytest.mark.django_db
def test_resync_resizes_pending_rows_after_charge(scheduled_booking: Booking) -> None:
    """+200 charge: percent deposit re-derives, pending balance absorbs the rest."""
    _add_charge(scheduled_booking, "200.00")

    PaymentScheduler.resync_for_booking(scheduled_booking)

    assert _row(scheduled_booking, PaymentPurpose.DEPOSIT).amount == Decimal("480.00")
    assert _row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("1120.00")


@pytest.mark.django_db
def test_charge_mutation_triggers_resync_via_signal(scheduled_booking: Booking) -> None:
    """The booking_total_changed receiver wires charge writes to the resync —
    no explicit service call anywhere in this test."""
    charge = _add_charge(scheduled_booking, "200.00")
    assert _row(scheduled_booking, PaymentPurpose.DEPOSIT).amount == Decimal("480.00")
    assert _row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("1120.00")

    charge.delete()
    assert _row(scheduled_booking, PaymentPurpose.DEPOSIT).amount == Decimal("420.00")
    assert _row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("980.00")


@pytest.mark.django_db
def test_resync_leaves_settled_deposit_untouched(scheduled_booking: Booking) -> None:
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    Payment.objects.filter(pk=deposit.pk).update(status=PaymentStatus.SUCCEEDED.value)

    _add_charge(scheduled_booking, "200.00")
    PaymentScheduler.resync_for_booking(scheduled_booking)

    # Settled deposit keeps its original 420; the pending balance carries
    # everything else: 1600 total - 420 committed = 1180.
    assert _row(scheduled_booking, PaymentPurpose.DEPOSIT).amount == Decimal("420.00")
    assert _row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("1180.00")


@pytest.mark.django_db
def test_resync_treats_processing_as_committed(scheduled_booking: Booking) -> None:
    """A PROCESSING row is mid-flight at the provider — resizing it would
    desync us from what the guest is actually paying."""
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    Payment.objects.filter(pk=deposit.pk).update(status=PaymentStatus.PROCESSING.value)

    _add_charge(scheduled_booking, "200.00")
    PaymentScheduler.resync_for_booking(scheduled_booking)

    assert _row(scheduled_booking, PaymentPurpose.DEPOSIT).amount == Decimal("420.00")
    assert _row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("1180.00")


@pytest.mark.django_db
def test_resync_all_settled_writes_residual_event(scheduled_booking: Booking) -> None:
    """Nothing left to resize: the residual is logged and lands on the
    booking Timeline (operators don't read Datadog)."""
    Payment.objects.filter(booking=scheduled_booking).update(status=PaymentStatus.SUCCEEDED.value)

    _add_charge(scheduled_booking, "200.00")

    assert _row(scheduled_booking, PaymentPurpose.DEPOSIT).amount == Decimal("420.00")
    assert _row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("980.00")

    event = BookingEvent.objects.filter(
        booking=scheduled_booking, reason="payment_schedule_residual"
    ).latest("created_at")
    assert event.meta["residual"] == "200.00"


@pytest.mark.django_db
def test_resync_clamps_pending_to_zero_on_overcollection(scheduled_booking: Booking) -> None:
    """A credit below what already settled clamps PENDING rows to 0 and
    records the negative residual; refunding stays an operator decision."""
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    Payment.objects.filter(pk=deposit.pk).update(status=PaymentStatus.SUCCEEDED.value)

    _add_charge(scheduled_booking, "-1100.00", label="Goodwill")
    PaymentScheduler.resync_for_booking(scheduled_booking)

    # Total 300 < settled 420 → balance clamps to 0, residual -120.
    assert _row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("0.00")
    event = BookingEvent.objects.filter(
        booking=scheduled_booking, reason="payment_schedule_residual"
    ).latest("created_at")
    assert event.meta["residual"] == "-120.00"


@pytest.mark.django_db
def test_resync_is_idempotent(scheduled_booking: Booking) -> None:
    _add_charge(scheduled_booking, "200.00")

    PaymentScheduler.resync_for_booking(scheduled_booking)
    PaymentScheduler.resync_for_booking(scheduled_booking)

    assert _row(scheduled_booking, PaymentPurpose.DEPOSIT).amount == Decimal("480.00")
    assert _row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("1120.00")
    assert Payment.objects.filter(booking=scheduled_booking).count() == 2


@pytest.mark.django_db
def test_resync_without_schedule_is_a_noop(booking: Any) -> None:
    """Pre-AWAITING_DEPOSIT (or financeless) bookings have no rows to resize;
    the eventual schedule sizes against the charges anyway."""
    fresh = Booking.objects.get(pk=booking.pk)
    _add_charge(fresh, "200.00")

    PaymentScheduler.resync_for_booking(fresh)

    assert not Payment.objects.filter(booking=fresh).exists()


@pytest.mark.django_db
def test_create_for_booking_sizes_against_charges(booking: Any, property_: Property) -> None:
    """A schedule created after charges exist includes them in the total."""
    _ensure_finance(property_)
    fresh = Booking.objects.get(pk=booking.pk)
    _add_charge(fresh, "200.00")

    PaymentScheduler.create_for_booking(fresh)

    assert _row(fresh, PaymentPurpose.DEPOSIT).amount == Decimal("480.00")
    assert _row(fresh, PaymentPurpose.BALANCE).amount == Decimal("1120.00")
