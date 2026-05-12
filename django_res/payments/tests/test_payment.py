"""Tests for the `Payment` model transitions and signals."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone as dj_timezone

from payments import signals as payment_signals
from payments.enums import (
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
)
from payments.models import Payment, PaymentEvent


@pytest.fixture
def deposit_payment(db: None, booking: Any, gbp: Any) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("420.00"),
        currency=gbp,
    )


@pytest.mark.django_db
def test_waive__transitions_to_waived_and_fires_signal(
    deposit_payment: Payment,
) -> None:
    captured: list[Payment] = []

    def receiver(sender: object, payment: Payment, **kwargs: object) -> None:
        captured.append(payment)

    payment_signals.payment_waived.connect(receiver)
    try:
        deposit_payment.waive("owner concession")
    finally:
        payment_signals.payment_waived.disconnect(receiver)

    deposit_payment.refresh_from_db()
    assert deposit_payment.status == PaymentStatus.WAIVED.value
    assert deposit_payment.failure_reason == "WAIVED:owner concession"
    assert captured == [deposit_payment]

    event = PaymentEvent.objects.get(payment=deposit_payment)
    assert event.from_status == PaymentStatus.PENDING.value
    assert event.to_status == PaymentStatus.WAIVED.value
    assert event.kind == "WAIVED"


@pytest.mark.django_db
def test_waive__rejects_from_terminal_status(deposit_payment: Payment) -> None:
    deposit_payment.status = PaymentStatus.SUCCEEDED.value
    deposit_payment.save(update_fields=["status"])
    with pytest.raises(ValueError):
        deposit_payment.waive("after-the-fact")


@pytest.mark.django_db
def test_mark_paid__transitions_to_succeeded_and_fires_signal(
    deposit_payment: Payment,
) -> None:
    captured: list[Payment] = []

    def receiver(sender: object, payment: Payment, **kwargs: object) -> None:
        captured.append(payment)

    payment_signals.payment_succeeded.connect(receiver)
    try:
        paid_at = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        deposit_payment.mark_paid(
            amount=Decimal("420.00"),
            paid_at=paid_at,
            method=PaymentMethod.BANK_TRANSFER.value,
            reference="bank-ref-123",
            notes="ops typed this in",
        )
    finally:
        payment_signals.payment_succeeded.disconnect(receiver)

    deposit_payment.refresh_from_db()
    assert deposit_payment.status == PaymentStatus.SUCCEEDED.value
    assert deposit_payment.provider == PaymentProvider.MANUAL_BANK_TRANSFER.value
    assert deposit_payment.provider_reference == "bank-ref-123"
    assert deposit_payment.payment_method == PaymentMethod.BANK_TRANSFER.value
    assert deposit_payment.settled_at == paid_at
    assert captured == [deposit_payment]

    event = PaymentEvent.objects.get(payment=deposit_payment, kind="MARK_PAID")
    assert event.from_status == PaymentStatus.PENDING.value
    assert event.to_status == PaymentStatus.SUCCEEDED.value


@pytest.mark.django_db
def test_transition_to__sets_settled_at_on_succeeded(
    deposit_payment: Payment,
) -> None:
    deposit_payment.transition_to(PaymentStatus.SUCCEEDED.value)
    deposit_payment.refresh_from_db()
    assert deposit_payment.settled_at is not None
    assert deposit_payment.settled_at <= dj_timezone.now()
