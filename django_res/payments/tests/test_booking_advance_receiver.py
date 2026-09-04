"""The payments-side receiver that advances a Booking when money settles.

`payment_succeeded` / `payment_waived` → `Booking.record_deposit` /
`Booking.record_balance` by `payment.purpose`. The receiver is defensive:
an `InvalidTransition` (double settlement, cancelled booking, out-of-order
balance) is logged as `payment.booking_advance_skipped` and swallowed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
import structlog.testing

from payments.enums import EventSource, PaymentPurpose, PaymentStatus
from payments.models import Payment
from payments.services import PaymentScheduler
from properties.models.finance import PropertyFinance
from reservations.enums import BookingStatus

if TYPE_CHECKING:
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import Booking

pytestmark = pytest.mark.django_db


def _payment(booking: Booking, gbp: Currency, purpose: str, **kwargs: object) -> Payment:
    defaults = {
        "booking": booking,
        "purpose": purpose,
        "amount": Decimal("700.00"),
        "currency": gbp,
    }
    defaults.update(kwargs)
    return Payment.objects.create(**defaults)


def _ensure_finance(property_: Property) -> PropertyFinance:
    """All-default finance row — mirrors `test_payment_scheduler.py`'s helper."""
    finance, _ = PropertyFinance.objects.get_or_create(property=property_)
    return finance


def _mark_paid(payment: Payment) -> Payment:
    return payment.mark_paid(
        payment.amount,
        datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        "bank_transfer",
        "BT-REF-1",
    )


def test_deposit_mark_paid_advances_booking_to_deposit_paid(
    booking: Booking, gbp: Currency
) -> None:
    payment = _payment(booking, gbp, PaymentPurpose.DEPOSIT.value)

    _mark_paid(payment)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.DEPOSIT_PAID.value


def test_deposit_succeeded_via_transition_to_advances_booking(
    booking: Booking, gbp: Currency
) -> None:
    payment = _payment(booking, gbp, PaymentPurpose.DEPOSIT.value)

    payment.transition_to(
        PaymentStatus.SUCCEEDED.value,
        source=EventSource.WEBHOOK.value,
    )

    booking.refresh_from_db()
    assert booking.status == BookingStatus.DEPOSIT_PAID.value


@pytest.mark.parametrize(
    "start_status",
    [BookingStatus.AWAITING_BALANCE.value, BookingStatus.DEPOSIT_PAID.value],
)
def test_balance_succeeded_advances_booking(
    booking: Booking, gbp: Currency, start_status: str
) -> None:
    booking.status = start_status
    booking.save(update_fields=["status"])
    payment = _payment(booking, gbp, PaymentPurpose.BALANCE.value)

    _mark_paid(payment)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.BALANCE_PAID.value


def test_deposit_waived_advances_booking(booking: Booking, gbp: Currency) -> None:
    payment = _payment(booking, gbp, PaymentPurpose.DEPOSIT.value)

    payment.waive("comp stay")

    booking.refresh_from_db()
    assert booking.status == BookingStatus.DEPOSIT_PAID.value


@pytest.mark.parametrize(
    "purpose",
    [PaymentPurpose.SECURITY_DEPOSIT.value, PaymentPurpose.CONCIERGE.value],
)
def test_non_rental_settlement_does_not_touch_booking(
    booking: Booking, gbp: Currency, purpose: str
) -> None:
    payment = _payment(booking, gbp, purpose)

    _mark_paid(payment)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value


def test_settlement_with_booking_already_advanced_is_idempotent_skip(
    booking: Booking, gbp: Currency
) -> None:
    """The seeding pattern: `record_*` runs before `mark_paid` — the receiver
    must treat the already-advanced booking as a no-op, not an error."""
    booking.record_deposit()
    payment = _payment(booking, gbp, PaymentPurpose.DEPOSIT.value)

    with structlog.testing.capture_logs() as logs:
        _mark_paid(payment)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.DEPOSIT_PAID.value
    skipped = [e for e in logs if e["event"] == "payment.booking_advance_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["payment_id"] == payment.pk
    assert skipped[0]["booking_id"] == booking.pk
    assert skipped[0]["booking_status"] == BookingStatus.DEPOSIT_PAID.value


def test_no_deposit_booking_balance_settle_advances_straight_to_balance_paid(
    booking: Booking, property_: Property
) -> None:
    """BUG-026: a booking that never wanted a deposit reaches BALANCE_PAID
    off its balance settling alone — no `payment.booking_advance_skipped`
    warning, since `skip_deposit()` already cleared the way at creation."""
    finance = _ensure_finance(property_)
    finance.deposit_required = False
    finance.save(update_fields=["deposit_required"])

    PaymentScheduler.create_for_booking(booking)
    booking.refresh_from_db()
    assert booking.status == BookingStatus.DEPOSIT_PAID.value
    balance = Payment.objects.get(booking=booking, purpose=PaymentPurpose.BALANCE.value)

    with structlog.testing.capture_logs() as logs:
        _mark_paid(balance)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.BALANCE_PAID.value
    assert not any(e["event"] == "payment.booking_advance_skipped" for e in logs)


def test_overcollection_root_cause_self_heals_via_resync(
    booking: Booking, property_: Property
) -> None:
    """BUG-026's reported root cause, end to end: the BALANCE settles first
    (for the full total, e.g. an operator-recorded manual payment) while the
    booking is still AWAITING_DEPOSIT — its own `record_balance()` call
    raises InvalidTransition and is swallowed. The next `resync_for_booking`
    (standing in for whatever real trigger fires `booking_total_changed`
    next) self-heals the booking straight to BALANCE_PAID."""
    _ensure_finance(property_)
    PaymentScheduler.create_for_booking(booking)
    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value
    balance = Payment.objects.get(booking=booking, purpose=PaymentPurpose.BALANCE.value)
    Payment.objects.filter(pk=balance.pk).update(amount=Decimal("1400.00"))
    balance.refresh_from_db()

    with structlog.testing.capture_logs() as logs:
        _mark_paid(balance)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.AWAITING_DEPOSIT.value
    skipped = [e for e in logs if e["event"] == "payment.booking_advance_skipped"]
    assert len(skipped) == 1

    PaymentScheduler.resync_for_booking(booking)

    booking.refresh_from_db()
    assert booking.status == BookingStatus.BALANCE_PAID.value


def test_settlement_on_cancelled_booking_logs_and_does_not_raise(
    booking: Booking, gbp: Currency
) -> None:
    """Cancel closes the PENDING schedule, but money already in flight at the
    gateway (PROCESSING) still lands; the booking-advance is skip-logged."""
    payment = _payment(
        booking, gbp, PaymentPurpose.DEPOSIT.value, status=PaymentStatus.PROCESSING.value
    )
    booking.cancel("guest withdrew")

    with structlog.testing.capture_logs() as logs:
        payment.transition_to(
            PaymentStatus.SUCCEEDED.value,
            source=EventSource.WEBHOOK.value,
        )

    booking.refresh_from_db()
    assert booking.status == BookingStatus.CANCELLED.value
    payment.refresh_from_db()
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert any(e["event"] == "payment.booking_advance_skipped" for e in logs)
