"""Tests for the `PaymentEvent` polymorphism constraint."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, transaction

from payments.enums import (
    PaymentPurpose,
    PaymentStatus,
    RefundPurposeTrack,
    RefundReasonCode,
    RefundStatus,
)
from payments.models import Payment, PaymentEvent, Refund


@pytest.mark.django_db
def test_payment_event__rejects_zero_fks(booking: Any, gbp: Any) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentEvent.objects.create(
            from_status="pending",
            to_status="succeeded",
        )


@pytest.mark.django_db
def test_payment_event__rejects_two_fks(booking: Any, gbp: Any) -> None:
    payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("100.00"),
        currency=gbp,
    )
    refund = Refund.objects.create(
        booking=booking,
        amount=Decimal("100.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        status=RefundStatus.PENDING.value,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PaymentEvent.objects.create(
            payment=payment,
            refund=refund,
            from_status="pending",
            to_status="approved",
        )


@pytest.mark.django_db
def test_payment_event__accepts_exactly_one_fk(
    booking: Any,
    gbp: Any,
) -> None:
    payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("100.00"),
        currency=gbp,
    )
    evt = PaymentEvent.objects.create(
        payment=payment,
        from_status="pending",
        to_status="succeeded",
    )
    assert evt.pk is not None
