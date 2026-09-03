"""Tests for `PaymentScheduler.resync_for_booking` — schedule resize on
charge-item changes (legacy regenerated the schedule on every modify).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from payments.enums import PaymentPurpose, PaymentStatus
from payments.models import Payment, PaymentEvent
from payments.services import PaymentScheduler
from properties.models import Property
from properties.models.finance import PropertyFinance
from reservations.enums import BookingStatus
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


def _set_deposit_required(property_: Property, required: bool) -> None:
    finance = PropertyFinance.objects.get_or_create(property=property_)[0]
    finance.deposit_required = required
    finance.save(update_fields=["deposit_required"])


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
    _set_deposit_required(property_, False)
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


# ---------------------------------------------------------------------------
# BUG-022/023: a zero deposit target cancels the PENDING deposit row (never a
# 0.00 PENDING row), and the mint arm is gated on the booking still awaiting
# its deposit.
# ---------------------------------------------------------------------------


def _pending_row(booking: Booking, purpose: PaymentPurpose) -> Payment:
    return Payment.objects.get(
        booking=booking, purpose=purpose.value, status=PaymentStatus.PENDING.value
    )


def _deposit_rows(booking: Booking, status: PaymentStatus | None = None) -> Any:
    qs = Payment.objects.filter(booking=booking, purpose=PaymentPurpose.DEPOSIT.value)
    return qs.filter(status=status.value) if status else qs


@pytest.mark.django_db
def test_resync_zero_override_cancels_pending_deposit(scheduled_booking: Booking) -> None:
    """BUG-022: override 0 means "no deposit" — the PENDING deposit row is
    cancelled (not resized to 0.00, which is unpayable and blocks the booking
    in AWAITING_DEPOSIT) and the balance absorbs the whole total."""
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    fresh = _set_override(scheduled_booking, Decimal("0"))

    PaymentScheduler.resync_for_booking(fresh)

    assert not _deposit_rows(fresh, PaymentStatus.PENDING).exists()
    deposit.refresh_from_db()
    assert deposit.status == PaymentStatus.CANCELLED.value
    assert deposit.amount == Decimal("420.00")  # last amount kept for audit
    assert _pending_row(fresh, PaymentPurpose.BALANCE).amount == Decimal("1400.00")
    event = PaymentEvent.objects.get(payment=deposit, kind="DEPOSIT_NOT_REQUIRED")
    assert (event.from_status, event.to_status) == (
        PaymentStatus.PENDING.value,
        PaymentStatus.CANCELLED.value,
    )
    assert not BookingEvent.objects.filter(
        booking=fresh, reason="payment_schedule_residual"
    ).exists()


@pytest.mark.django_db
def test_resync_zero_override_is_idempotent(scheduled_booking: Booking) -> None:
    fresh = _set_override(scheduled_booking, Decimal("0"))

    PaymentScheduler.resync_for_booking(fresh)
    PaymentScheduler.resync_for_booking(fresh)

    assert _deposit_rows(fresh).count() == 1
    assert _deposit_rows(fresh, PaymentStatus.CANCELLED).count() == 1
    assert PaymentEvent.objects.filter(kind="DEPOSIT_NOT_REQUIRED").count() == 1
    assert _pending_row(fresh, PaymentPurpose.BALANCE).amount == Decimal("1400.00")


@pytest.mark.django_db
def test_zero_override_then_positive_override_mints_fresh_deposit(
    scheduled_booking: Booking,
) -> None:
    """The cancelled row frees the unique-active slot; a later override mints
    a fresh PENDING deposit rather than resurrecting the old one."""
    old = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    PaymentScheduler.resync_for_booking(_set_override(scheduled_booking, Decimal("0")))

    fresh = _set_override(scheduled_booking, Decimal("500.00"))
    PaymentScheduler.resync_for_booking(fresh)

    minted = _pending_row(fresh, PaymentPurpose.DEPOSIT)
    assert minted.pk != old.pk
    assert minted.amount == Decimal("500.00")
    assert _pending_row(fresh, PaymentPurpose.BALANCE).amount == Decimal("900.00")


@pytest.mark.django_db
def test_zero_override_then_clear_remints_policy_deposit(scheduled_booking: Booking) -> None:
    """Clearing a zero override on a deposit-required property brings the
    policy deposit back (the mint arm no longer needs an override)."""
    old = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    PaymentScheduler.resync_for_booking(_set_override(scheduled_booking, Decimal("0")))

    fresh = _set_override(scheduled_booking, None)
    PaymentScheduler.resync_for_booking(fresh)

    minted = _pending_row(fresh, PaymentPurpose.DEPOSIT)
    assert minted.pk != old.pk
    assert minted.amount == Decimal("420.00")
    assert _pending_row(fresh, PaymentPurpose.BALANCE).amount == Decimal("980.00")


@pytest.mark.django_db
def test_overcollection_cancels_pending_deposit(scheduled_booking: Booking) -> None:
    """Nothing left to collect: the PENDING deposit is cancelled rather than
    clamped to 0.00; the negative residual is still recorded for ops."""
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    balance = _row(scheduled_booking, PaymentPurpose.BALANCE)
    Payment.objects.filter(pk=balance.pk).update(
        status=PaymentStatus.SUCCEEDED.value, amount=Decimal("1500.00")
    )

    PaymentScheduler.resync_for_booking(scheduled_booking)

    deposit.refresh_from_db()
    assert deposit.status == PaymentStatus.CANCELLED.value
    assert not _deposit_rows(scheduled_booking, PaymentStatus.PENDING).exists()
    # Audit says "covered", not "not required" — the policy still wants one.
    assert PaymentEvent.objects.filter(payment=deposit, kind="DEPOSIT_COVERED").count() == 1
    event = BookingEvent.objects.filter(
        booking=scheduled_booking, reason="payment_schedule_residual"
    ).latest("created_at")
    assert event.meta["residual"] == "-100.00"


@pytest.mark.django_db
def test_resync_remints_failed_policy_deposit_without_override(
    scheduled_booking: Booking,
) -> None:
    """A FAILED deposit on a still-awaiting booking is re-minted from policy on
    the next resync — the only retry path — with a fresh `due_at` so the
    expiry window restarts."""
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    Payment.objects.filter(pk=deposit.pk).update(status=PaymentStatus.FAILED.value)

    _add_charge(scheduled_booking, "200.00")  # resync via signal, no override

    minted = _pending_row(scheduled_booking, PaymentPurpose.DEPOSIT)
    assert minted.pk != deposit.pk
    assert minted.amount == Decimal("480.00")
    assert minted.due_at is not None
    assert abs((timezone.now() - minted.due_at).total_seconds()) < 5
    assert _pending_row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("1120.00")


@pytest.mark.django_db
def test_resync_does_not_mint_deposit_after_waive(scheduled_booking: Booking) -> None:
    """WAIVED is non-active but the booking has advanced to DEPOSIT_PAID —
    a later charge edit must not mint a fresh deposit onto a paid booking."""
    _row(scheduled_booking, PaymentPurpose.DEPOSIT).waive("goodwill")
    fresh = Booking.objects.get(pk=scheduled_booking.pk)
    assert fresh.status == BookingStatus.DEPOSIT_PAID.value

    _add_charge(fresh, "200.00")

    assert _deposit_rows(fresh).count() == 1
    assert _deposit_rows(fresh, PaymentStatus.WAIVED).count() == 1
    assert _pending_row(fresh, PaymentPurpose.BALANCE).amount == Decimal("1600.00")


@pytest.mark.django_db
def test_resync_does_not_mint_deposit_once_booking_advanced(
    scheduled_booking: Booking,
) -> None:
    """A FAILED deposit on a booking already past AWAITING_DEPOSIT (ops moved
    it on by hand) is not re-minted."""
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    Payment.objects.filter(pk=deposit.pk).update(status=PaymentStatus.FAILED.value)
    Booking.objects.filter(pk=scheduled_booking.pk).update(status=BookingStatus.DEPOSIT_PAID.value)
    fresh = Booking.objects.get(pk=scheduled_booking.pk)

    _add_charge(fresh, "200.00")

    assert _deposit_rows(fresh).count() == 1
    assert _pending_row(fresh, PaymentPurpose.BALANCE).amount == Decimal("1600.00")


@pytest.mark.django_db
def test_resync_on_closed_booking_does_not_mint(scheduled_booking: Booking) -> None:
    """A cancelled booking's schedule rows are all terminal; a stray resync
    must not mint a new deposit onto it."""
    scheduled_booking.cancel("guest changed plans")
    fresh = Booking.objects.get(pk=scheduled_booking.pk)
    assert not Payment.objects.filter(booking=fresh, status=PaymentStatus.PENDING.value).exists()

    PaymentScheduler.resync_for_booking(fresh)

    assert Payment.objects.filter(booking=fresh).count() == 2
    assert not Payment.objects.filter(booking=fresh, status=PaymentStatus.PENDING.value).exists()


@pytest.mark.django_db
def test_resync_on_deposit_optional_property_never_mints_without_override(
    booking: Any, property_: Property
) -> None:
    """BUG-023 half of the mint gate: a `deposit_required=False` property
    gets no deposit from resync unless an override asks for one — the
    generalised mint arm must not grow a policy deposit on a charge edit."""
    _set_deposit_required(property_, False)
    fresh = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.create_for_booking(fresh)
    assert not _deposit_rows(fresh).exists()

    _add_charge(fresh, "200.00")

    assert not _deposit_rows(fresh).exists()
    assert _pending_row(fresh, PaymentPurpose.BALANCE).amount == Decimal("1600.00")


# ---------------------------------------------------------------------------
# BUG-023: the policy branch honours `deposit_required`, and property policy
# is live for unsettled schedules (decision 4).
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_clearing_override_on_deposit_optional_property_removes_deposit(
    booking: Any, property_: Property
) -> None:
    """BUG-023: on a `deposit_required=False` property an override mints a
    deposit; clearing it must remove that deposit again, not re-size it to
    the policy percentage the property has opted out of."""
    _set_deposit_required(property_, False)
    fresh = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.create_for_booking(fresh)
    assert not _deposit_rows(fresh).exists()

    overridden = _set_override(fresh, Decimal("500.00"))
    PaymentScheduler.resync_for_booking(overridden)
    minted = _pending_row(overridden, PaymentPurpose.DEPOSIT)
    assert minted.amount == Decimal("500.00")
    assert _pending_row(overridden, PaymentPurpose.BALANCE).amount == Decimal("900.00")

    cleared = _set_override(overridden, None)
    PaymentScheduler.resync_for_booking(cleared)

    assert not _deposit_rows(cleared, PaymentStatus.PENDING).exists()
    minted.refresh_from_db()
    assert minted.status == PaymentStatus.CANCELLED.value
    assert PaymentEvent.objects.filter(payment=minted, kind="DEPOSIT_NOT_REQUIRED").count() == 1
    assert _pending_row(cleared, PaymentPurpose.BALANCE).amount == Decimal("1400.00")


@pytest.mark.django_db
def test_policy_flip_to_not_required_cancels_pending_deposit(
    scheduled_booking: Booking, property_: Property
) -> None:
    """Property policy is live for unsettled schedules: switching the deposit
    off cancels the PENDING deposit on the next resync."""
    deposit = _row(scheduled_booking, PaymentPurpose.DEPOSIT)
    _set_deposit_required(property_, False)

    PaymentScheduler.resync_for_booking(Booking.objects.get(pk=scheduled_booking.pk))

    assert not _deposit_rows(scheduled_booking, PaymentStatus.PENDING).exists()
    deposit.refresh_from_db()
    assert deposit.status == PaymentStatus.CANCELLED.value
    assert deposit.amount == Decimal("420.00")  # last amount kept for audit
    assert PaymentEvent.objects.filter(payment=deposit, kind="DEPOSIT_NOT_REQUIRED").count() == 1
    assert _pending_row(scheduled_booking, PaymentPurpose.BALANCE).amount == Decimal("1400.00")
    # The cancelled row leaves `pending`, so the schedule still reconciles.
    assert not BookingEvent.objects.filter(
        booking=scheduled_booking, reason="payment_schedule_residual"
    ).exists()


@pytest.mark.django_db
def test_policy_flip_to_required_mints_deposit_while_awaiting(
    booking: Any, property_: Property
) -> None:
    """...and switching it on mints the policy deposit while the booking is
    still AWAITING_DEPOSIT."""
    _set_deposit_required(property_, False)
    fresh = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.create_for_booking(fresh)
    assert not _deposit_rows(fresh).exists()

    _set_deposit_required(property_, True)
    PaymentScheduler.resync_for_booking(Booking.objects.get(pk=booking.pk))

    assert _pending_row(fresh, PaymentPurpose.DEPOSIT).amount == Decimal("420.00")
    assert _pending_row(fresh, PaymentPurpose.BALANCE).amount == Decimal("980.00")


@pytest.mark.django_db
def test_policy_flip_to_required_does_not_mint_once_advanced(
    booking: Any, property_: Property
) -> None:
    """A booking that has moved past AWAITING_DEPOSIT keeps its no-deposit
    schedule when the property later switches deposits on."""
    _set_deposit_required(property_, False)
    fresh = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.create_for_booking(fresh)
    Booking.objects.filter(pk=fresh.pk).update(status=BookingStatus.DEPOSIT_PAID.value)

    _set_deposit_required(property_, True)
    PaymentScheduler.resync_for_booking(Booking.objects.get(pk=booking.pk))

    assert not _deposit_rows(fresh).exists()
    assert _pending_row(fresh, PaymentPurpose.BALANCE).amount == Decimal("1400.00")
