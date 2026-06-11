"""Payment/Refund transition guards must check current DB state under lock.

Mirrors `reservations/tests/test_transition_locking.py` — the stale-instance
pattern stands in for the concurrent double-click: the second caller's
in-memory status passes the old guard, so only a lock + re-read stops the
double transition (duplicate `payment_succeeded`, duplicate gateway refund).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from core.exceptions import InvalidTransition
from payments.enums import PaymentPurpose, PaymentStatus, RefundMethod, RefundStatus
from payments.models import Payment, PaymentEvent, Refund
from payments.services.refund import RefundService
from pricing.models import Currency
from reservations.models import Booking


@pytest.fixture
def pending_deposit(db: None, booking: Booking, gbp: Currency) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        amount=Decimal("420.00"),
        currency=gbp,
        status=PaymentStatus.PENDING.value,
    )


@pytest.mark.django_db
def test_payment_transition_refuses_stale_instance(pending_deposit: Payment) -> None:
    stale = Payment.objects.get(pk=pending_deposit.pk)
    pending_deposit.mark_paid(
        amount=Decimal("420.00"),
        paid_at=timezone.now(),
        method="bank_transfer",
        reference="BT-1",
    )

    with pytest.raises(InvalidTransition):
        stale.transition_to(PaymentStatus.SUCCEEDED.value)

    succeeded_events = PaymentEvent.objects.filter(
        payment=pending_deposit,
        to_status=PaymentStatus.SUCCEEDED.value,
    )
    assert succeeded_events.count() == 1


@pytest.mark.django_db
def test_refund_model_transition_enforces_allowed_table(booking: Booking, gbp: Currency) -> None:
    """`Refund._transition` had no allowed-transitions table — any direct
    caller could jump PENDING straight to SUCCEEDED."""
    refund = Refund.objects.create(
        booking=booking,
        amount=Decimal("100.00"),
        currency=gbp,
        status=RefundStatus.PENDING.value,
        purpose_track="balance",
        reason_code="cancellation",
        method=RefundMethod.MANUAL_BANK_TRANSFER.value,
    )

    with pytest.raises(InvalidTransition):
        refund._transition(RefundStatus.SUCCEEDED.value)

    refund.refresh_from_db()
    assert refund.status == RefundStatus.PENDING.value


@pytest.mark.django_db
def test_refund_execute_retry_with_stale_instance_is_idempotent(
    booking: Booking, gbp: Currency
) -> None:
    """A stale double-execute must return the settled refund, not mint a
    second outbound gateway payment."""
    refund = RefundService.request(
        booking=booking,
        amount=Decimal("100.00"),
        currency=gbp,
        purpose_track="balance",
        reason_code="cancellation",
        method=RefundMethod.MANUAL_BANK_TRANSFER.value,
    )
    RefundService.approve(refund, actor=None)
    stale = Refund.objects.get(pk=refund.pk)

    RefundService.execute(refund, actor=None)
    refund.refresh_from_db()
    assert refund.status == RefundStatus.SUCCEEDED.value

    result = RefundService.execute(stale, actor=None)

    assert result.status == RefundStatus.SUCCEEDED.value
    outbound = Payment.objects.filter(
        booking=booking,
        purpose=PaymentPurpose.REFUND.value,
        meta__refund_id=refund.pk,
    )
    assert outbound.count() == 1
