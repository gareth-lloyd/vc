"""Money bookkeeping when a booking closes (CANCELLED / DECLINED / EXPIRED).

The legacy app did nothing on cancel and the design spec leaves refund
policy as a future workflow — so the contract here is deliberately
bookkeeping-only: unpaid PENDING rows close with the booking (freeing the
one-active-row-per-purpose slots), settled money is never touched
(refunds stay a manual operator workflow), and a security deposit holding
real money is flagged for ops review rather than auto-released.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import structlog
from django.utils import timezone

from payments.enums import (
    PaymentPurpose,
    PaymentStatus,
    SecurityDepositKind,
    SecurityDepositStatus,
)
from payments.models import Payment, PaymentEvent, SecurityDeposit
from pricing.models import Currency
from reservations.enums import BookingStatus
from reservations.models import Booking


def _pending(booking: Booking, gbp: Currency, purpose: str, amount: str) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=purpose,
        amount=Decimal(amount),
        currency=gbp,
        status=PaymentStatus.PENDING.value,
    )


@pytest.mark.django_db
def test_cancel_booking_cancels_pending_payments(booking: Booking, gbp: Currency) -> None:
    deposit = _pending(booking, gbp, PaymentPurpose.DEPOSIT.value, "420.00")
    balance = _pending(booking, gbp, PaymentPurpose.BALANCE.value, "980.00")

    booking.cancel("guest changed plans")

    deposit.refresh_from_db()
    balance.refresh_from_db()
    assert deposit.status == PaymentStatus.CANCELLED.value
    assert balance.status == PaymentStatus.CANCELLED.value
    events = PaymentEvent.objects.filter(kind="BOOKING_CANCELLED")
    assert events.count() == 2


@pytest.mark.django_db
def test_decline_booking_cancels_pending_payments(booking: Booking, gbp: Currency) -> None:
    booking.status = BookingStatus.PENDING_OWNER_APPROVAL.value
    booking.save(update_fields=["status"])
    deposit = _pending(booking, gbp, PaymentPurpose.DEPOSIT.value, "420.00")

    booking.owner_decline("dates no longer work")

    deposit.refresh_from_db()
    assert deposit.status == PaymentStatus.CANCELLED.value
    assert PaymentEvent.objects.filter(kind="BOOKING_DECLINED").count() == 1


@pytest.mark.django_db
def test_cancel_booking_leaves_settled_payments_untouched(booking: Booking, gbp: Currency) -> None:
    """No automatic refunds — settled money is an operator decision."""
    paid = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("420.00"),
        currency=gbp,
        status=PaymentStatus.SUCCEEDED.value,
        settled_at=timezone.now(),
    )

    booking.cancel("guest changed plans")

    paid.refresh_from_db()
    assert paid.status == PaymentStatus.SUCCEEDED.value


@pytest.mark.django_db
def test_cancel_booking_fails_awaiting_security_deposit(booking: Booking, gbp: Currency) -> None:
    """An SD that holds no money yet closes with the booking."""
    sd = SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.BT_REFUNDABLE.value,
        status=SecurityDepositStatus.AWAITING_BT.value,
        amount=Decimal("500.00"),
        currency=gbp,
    )

    booking.cancel("guest changed plans")

    sd.refresh_from_db()
    assert sd.status == SecurityDepositStatus.FAILED.value


@pytest.mark.django_db
def test_cancel_booking_flags_held_security_deposit_for_review(
    booking: Booking, gbp: Currency
) -> None:
    """An SD holding real money must NOT auto-release — ops decides."""
    sd = SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        status=SecurityDepositStatus.PRE_AUTHED.value,
        amount=Decimal("500.00"),
        currency=gbp,
    )

    with structlog.testing.capture_logs() as logs:
        booking.cancel("guest changed plans")

    sd.refresh_from_db()
    assert sd.status == SecurityDepositStatus.PRE_AUTHED.value
    flagged = [log for log in logs if log["event"] == "payment.sd_review_required"]
    assert len(flagged) == 1
    assert flagged[0]["security_deposit_id"] == sd.pk


@pytest.mark.django_db
def test_expired_booking_still_expires_pending_payments(booking: Booking, gbp: Currency) -> None:
    """The pre-existing EXPIRED contract survives the generalisation."""
    deposit = _pending(booking, gbp, PaymentPurpose.DEPOSIT.value, "420.00")

    booking.expire()

    deposit.refresh_from_db()
    assert deposit.status == PaymentStatus.EXPIRED.value
    assert PaymentEvent.objects.filter(kind="BOOKING_EXPIRED").count() == 1
