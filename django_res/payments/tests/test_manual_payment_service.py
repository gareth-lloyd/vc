"""`ManualPaymentService.record` — the service behind the track-payments POST.

FG-012: manual rows must be created through the service layer (born PENDING,
idempotent on an optional `idempotency_key`) rather than minted in the view
straight from `request.data`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.idempotency import IDEMPOTENCY_META_KEY
from payments.enums import PaymentMethod, PaymentPurpose, PaymentStatus
from payments.models import Payment
from payments.services.manual_payment import ManualPaymentService
from reservations.models import Booking


@pytest.mark.django_db
def test_record_creates_pending_payment(booking: Booking) -> None:
    payment = ManualPaymentService.record(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("100.00"),
        payment_method=PaymentMethod.BANK_TRANSFER.value,
    )

    assert payment.status == PaymentStatus.PENDING.value
    assert payment.amount == Decimal("100.00")
    assert payment.currency == booking.currency
    assert payment.purpose == PaymentPurpose.DEPOSIT.value


@pytest.mark.django_db
def test_record_with_idempotency_key_returns_original_row(booking: Booking) -> None:
    first = ManualPaymentService.record(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("100.00"),
        idempotency_key="op-click-1",
    )
    second = ManualPaymentService.record(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("999.00"),  # replay payloads may drift — the original wins
        idempotency_key="op-click-1",
    )

    assert second.pk == first.pk
    assert second.amount == Decimal("100.00")
    assert Payment.objects.filter(booking=booking).count() == 1
    assert first.meta[IDEMPOTENCY_META_KEY] == "op-click-1"


@pytest.mark.django_db
def test_record_idempotency_is_scoped_to_booking_and_purpose(booking: Booking) -> None:
    """The same key string on a different purpose is a different operation."""
    deposit = ManualPaymentService.record(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("100.00"),
        idempotency_key="shared-key",
    )
    balance = ManualPaymentService.record(
        booking=booking,
        purpose=PaymentPurpose.BALANCE.value,
        amount=Decimal("200.00"),
        idempotency_key="shared-key",
    )

    assert balance.pk != deposit.pk
    assert Payment.objects.filter(booking=booking).count() == 2


@pytest.mark.django_db
def test_record_without_key_does_not_stamp_meta(booking: Booking) -> None:
    payment = ManualPaymentService.record(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("100.00"),
        meta={"note": "kept"},
    )

    assert IDEMPOTENCY_META_KEY not in payment.meta
    assert payment.meta["note"] == "kept"
