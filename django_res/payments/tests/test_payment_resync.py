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
from properties.models.finance import PropertyFinance
from reservations.models import Booking, BookingChargeItem, BookingEvent


def _ensure_finance(property_: Property) -> None:
    """All-default finance row — the scheduler reads the policy floor."""
    PropertyFinance.objects.get_or_create(property=property_)


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


# ---------------------------------------------------------------------------
# GAP-087: per-booking deposit override honoured (and made durable) by resync
# ---------------------------------------------------------------------------


def _set_override(booking: Booking, amount: Decimal | None) -> Booking:
    """Persist the override and return a booking instance carrying it."""
    Booking.objects.filter(pk=booking.pk).update(deposit_override_amount=amount)
    return Booking.objects.get(pk=booking.pk)


@pytest.mark.django_db
def test_resync_honours_override(scheduled_booking: Booking) -> None:
    """Setting an override resizes the PENDING deposit; balance is the remainder."""
    fresh = _set_override(scheduled_booking, Decimal("500.00"))

    PaymentScheduler.resync_for_booking(fresh)

    assert _row(fresh, PaymentPurpose.DEPOSIT).amount == Decimal("500.00")
    assert _row(fresh, PaymentPurpose.BALANCE).amount == Decimal("900.00")


@pytest.mark.django_db
def test_override_survives_resync_after_charge(scheduled_booking: Booking) -> None:
    """The crux: an override is not clobbered when a charge triggers a resync.

    Without the override the 30% policy would re-derive the deposit to 480 on a
    1600 total; with it the deposit stays pinned at 500 and only the balance
    absorbs the +200 charge.
    """
    fresh = _set_override(scheduled_booking, Decimal("500.00"))

    # Charge write fires booking_total_changed → resync via the signal, passing
    # the charge's `booking` (loaded with the override, as it is in production).
    _add_charge(fresh, "200.00")

    assert _row(fresh, PaymentPurpose.DEPOSIT).amount == Decimal("500.00")
    assert _row(fresh, PaymentPurpose.BALANCE).amount == Decimal("1100.00")


@pytest.mark.django_db
def test_clearing_override_reverts_to_policy(scheduled_booking: Booking) -> None:
    """Nulling the override returns the deposit to the property policy figure."""
    fresh = _set_override(scheduled_booking, Decimal("500.00"))
    PaymentScheduler.resync_for_booking(fresh)
    assert _row(fresh, PaymentPurpose.DEPOSIT).amount == Decimal("500.00")

    reverted = _set_override(fresh, None)
    PaymentScheduler.resync_for_booking(reverted)

    assert _row(reverted, PaymentPurpose.DEPOSIT).amount == Decimal("420.00")
    assert _row(reverted, PaymentPurpose.BALANCE).amount == Decimal("980.00")


@pytest.mark.django_db
def test_resync_mints_deposit_row_when_override_set_and_none_exists(
    booking: Any, property_: Property
) -> None:
    """B1: policy `deposit_required=False` creates no deposit row; an override
    then makes resync *mint* one (the durable post-creation path)."""
    finance = PropertyFinance.objects.get_or_create(property=property_)[0]
    finance.deposit_required = False
    finance.save(update_fields=["deposit_required"])
    fresh = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.create_for_booking(fresh)
    assert not Payment.objects.filter(booking=fresh, purpose=PaymentPurpose.DEPOSIT.value).exists()

    overridden = _set_override(fresh, Decimal("500.00"))
    PaymentScheduler.resync_for_booking(overridden)

    assert _row(overridden, PaymentPurpose.DEPOSIT).amount == Decimal("500.00")
    assert _row(overridden, PaymentPurpose.BALANCE).amount == Decimal("900.00")


@pytest.mark.django_db
def test_resync_override_clamps_to_total(scheduled_booking: Booking) -> None:
    """An override above the total clamps the deposit to the total, balance 0."""
    fresh = _set_override(scheduled_booking, Decimal("2000.00"))

    PaymentScheduler.resync_for_booking(fresh)

    assert _row(fresh, PaymentPurpose.DEPOSIT).amount == Decimal("1400.00")
    assert _row(fresh, PaymentPurpose.BALANCE).amount == Decimal("0.00")


@pytest.mark.django_db
def test_resync_does_not_mint_second_deposit_when_settled(scheduled_booking: Booking) -> None:
    """A SUCCEEDED deposit already exists — an override must not mint a rival row."""
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    Payment.objects.filter(pk=deposit.pk).update(status=PaymentStatus.SUCCEEDED.value)

    fresh = _set_override(scheduled_booking, Decimal("500.00"))
    PaymentScheduler.resync_for_booking(fresh)

    assert Payment.objects.filter(booking=fresh, purpose=PaymentPurpose.DEPOSIT.value).count() == 1
    # Settled deposit keeps its 420; balance carries the rest (1400 - 420).
    assert _row(fresh, PaymentPurpose.DEPOSIT).amount == Decimal("420.00")
    assert _row(fresh, PaymentPurpose.BALANCE).amount == Decimal("980.00")


@pytest.mark.django_db
def test_resync_mints_deposit_when_only_a_failed_deposit_exists(
    scheduled_booking: Booking,
) -> None:
    """A FAILED deposit is not active — an override must still mint a live one.

    Regression guard: a failed deposit attempt leaves the booking in
    AWAITING_DEPOSIT with a FAILED (non-active) deposit row. Setting an override
    must mint a fresh PENDING deposit (the unique-active constraint permits it),
    not silently no-op because *some* deposit row exists.
    """
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    Payment.objects.filter(pk=deposit.pk).update(status=PaymentStatus.FAILED.value)

    fresh = _set_override(scheduled_booking, Decimal("500.00"))
    PaymentScheduler.resync_for_booking(fresh)

    active = Payment.objects.filter(
        booking=fresh,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.PENDING.value,
    )
    assert active.count() == 1
    assert active.get().amount == Decimal("500.00")
    assert _row(fresh, PaymentPurpose.BALANCE).amount == Decimal("900.00")
