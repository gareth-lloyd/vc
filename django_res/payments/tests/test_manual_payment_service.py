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
def test_duplicate_key_same_booking_and_purpose_hits_db_backstop(booking: Booking) -> None:
    """FG-010: the service's check-then-create is not race-proof on its own.

    Two concurrent `record(...)` calls with the same key both pass
    `find_by_meta_key` under READ COMMITTED; the partial unique index on
    `(booking, purpose, meta->>'idempotency_key')` is the DB floor that
    makes the loser fail loudly. Simulated by writing the duplicate row
    directly, bypassing the pre-check. Uses CONCIERGE (many-per-booking, no
    active-row constraint) so the only constraint in play is the key one.
    """
    from django.db import IntegrityError

    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.CONCIERGE.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("100.00"),
        currency=booking.currency,
        meta={IDEMPOTENCY_META_KEY: "op-click-1"},
    )
    with pytest.raises(IntegrityError, match="payment_idempotency_key_unique"):
        Payment.objects.create(
            booking=booking,
            purpose=PaymentPurpose.CONCIERGE.value,
            status=PaymentStatus.PENDING.value,
            amount=Decimal("100.00"),
            currency=booking.currency,
            meta={IDEMPOTENCY_META_KEY: "op-click-1"},
        )


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
