"""Tests for `Refund` workflow + `RefundService`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
import structlog.testing
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction

from payments.enums import (
    PaymentPurpose,
    PaymentStatus,
    RefundMethod,
    RefundPurposeTrack,
    RefundReasonCode,
    RefundStatus,
)
from payments.models import Payment, Refund
from payments.services.refund import RefundService


def _grant(user: Any, *codenames: str) -> None:
    """Attach the named auth permissions to a User row."""
    for codename in codenames:
        perm = Permission.objects.get(codename=codename)
        user.user_permissions.add(perm)


@pytest.fixture
def paid_deposit(db: None, booking: Any, gbp: Any) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.DEPOSIT.value,
        status=PaymentStatus.SUCCEEDED.value,
        amount=Decimal("420.00"),
        currency=gbp,
    )


@pytest.fixture
def paid_balance(db: None, booking: Any, gbp: Any) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.BALANCE.value,
        status=PaymentStatus.SUCCEEDED.value,
        amount=Decimal("980.00"),
        currency=gbp,
    )


@pytest.mark.django_db
def test_refund_state_machine__request_approve_execute_creates_payment(
    booking: Any,
    gbp: Any,
    paid_deposit: Payment,
    user: Any,
    approver: Any,
) -> None:
    _grant(approver, "approve_refund", "execute_refund", "self_approve_refund")
    refund = RefundService.request(
        booking=booking,
        amount=Decimal("100.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
    )
    assert refund.status == RefundStatus.PENDING.value

    RefundService.approve(refund, actor=approver)
    refund.refresh_from_db()
    assert refund.status == RefundStatus.APPROVED.value
    assert refund.approved_by_id == approver.pk

    RefundService.execute(refund, actor=approver)
    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value

    linked = Payment.objects.get(
        booking=booking,
        purpose=PaymentPurpose.REFUND.value,
    )
    assert linked.status == PaymentStatus.PROCESSING.value
    assert linked.meta == {"refund_id": refund.pk}


@pytest.mark.django_db
def test_refund_approve__rejects_self_approval_without_permission(
    booking: Any,
    gbp: Any,
    paid_deposit: Payment,
    user: Any,
) -> None:
    _grant(user, "approve_refund")  # user has perm but is the requester
    refund = RefundService.request(
        booking=booking,
        amount=Decimal("50.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
    )
    with pytest.raises(PermissionError):
        RefundService.approve(refund, actor=user)


@pytest.mark.django_db
def test_refund_approve__rejects_self_approval_even_with_self_approve_perm(
    booking: Any,
    gbp: Any,
    paid_deposit: Payment,
    user: Any,
) -> None:
    """BUG-010: `self_approve_refund` must not bypass approval SoD.

    The DB CheckConstraint unconditionally forbids `approved_by ==
    requested_by`, so a permission bypass at :approve could only ever end
    in an IntegrityError 500. The service must reject with a clean
    PermissionError instead; the perm's bypass applies to :execute only.
    """
    _grant(user, "approve_refund", "self_approve_refund")
    refund = RefundService.request(
        booking=booking,
        amount=Decimal("50.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
    )
    with pytest.raises(PermissionError):
        RefundService.approve(refund, actor=user)
    refund.refresh_from_db()
    assert refund.status == RefundStatus.PENDING.value
    assert refund.approved_by_id is None


@pytest.mark.django_db
def test_refund_db_constraint__separation_of_duties_floor(
    booking: Any,
    gbp: Any,
    user: Any,
) -> None:
    refund = Refund(
        booking=booking,
        amount=Decimal("50.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        requested_by=user,
        approved_by=user,  # same user — DB check should reject
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        refund.save()


@pytest.mark.django_db
def test_refund_execute__permits_approver_when_self_approve_perm_present(
    booking: Any,
    gbp: Any,
    paid_deposit: Payment,
    user: Any,
    approver: Any,
) -> None:
    _grant(approver, "approve_refund", "execute_refund")
    refund = RefundService.request(
        booking=booking,
        amount=Decimal("50.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
    )
    RefundService.approve(refund, actor=approver)

    # Approver normally cannot also execute (no self_approve perm).
    with pytest.raises(PermissionError):
        RefundService.execute(refund, actor=approver)

    # Grant `self_approve_refund`; the same approver can now execute.
    _grant(approver, "self_approve_refund")
    # Reload to refresh the user-permission cache.
    from accounts.models import User

    fresh = User.objects.get(pk=approver.pk)
    RefundService.execute(refund, actor=fresh)
    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value


def _configure_cancellation(
    property_: Any,
    *,
    fee_amount: Decimal,
    fee_percent: Decimal,
) -> None:
    from properties.models.finance import GroupFinance, PropertyFinance

    gf, _ = GroupFinance.objects.get_or_create(group=property_.group)
    gf.cancellation_fee_amount = fee_amount
    gf.cancellation_fee_percent = fee_percent
    gf.save(update_fields=["cancellation_fee_amount", "cancellation_fee_percent"])
    PropertyFinance.objects.get_or_create(property=property_)


@pytest.mark.django_db
def test_from_cancellation__computes_refundable_minus_fee(
    booking: Any,
    property_: Any,
    paid_deposit: Payment,
    paid_balance: Payment,
    user: Any,
) -> None:
    # Flat fee 200 vs percent 10% of 1400 = 140 → max = 200. Refundable = 1200.
    _configure_cancellation(
        property_,
        fee_amount=Decimal("200.00"),
        fee_percent=Decimal("10.00"),
    )
    # Re-fetch the booking so cached `property.finance` reflects the new row.
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    refund = RefundService.from_cancellation(
        booking,
        reason="guest cancelled",
        requested_by=user,
    )
    assert refund is not None
    assert refund.amount == Decimal("1200.00")
    assert refund.reason_code == RefundReasonCode.CANCELLATION.value


@pytest.mark.django_db
def test_request__is_idempotent_when_same_key_supplied(
    booking: Any,
    gbp: Any,
    paid_deposit: Payment,
    user: Any,
) -> None:
    """A second :request with the same key returns the first Refund.

    Webhook retries from the payment gateway are the canonical retry
    path — the gateway can deliver the same event twice. Without an
    idempotency guard the second delivery would either open a duplicate
    refund or fail the cumulative-amount check.
    """
    key = "evt_abc123"
    first = RefundService.request(
        booking=booking,
        amount=Decimal("100.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
        idempotency_key=key,
    )
    second = RefundService.request(
        booking=booking,
        amount=Decimal("100.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
        idempotency_key=key,
    )
    assert second.pk == first.pk
    assert Refund.objects.filter(booking=booking).count() == 1
    assert first.meta["idempotency_key"] == key


@pytest.mark.django_db
def test_request__no_key_means_no_idempotency(
    booking: Any,
    gbp: Any,
    paid_deposit: Payment,
    user: Any,
) -> None:
    """Without `idempotency_key`, repeat calls behave as before — two rows.

    Internal callers (tests, management commands) that don't propagate
    an external trigger ID must remain free to open multiple refunds.
    """
    first = RefundService.request(
        booking=booking,
        amount=Decimal("50.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
    )
    second = RefundService.request(
        booking=booking,
        amount=Decimal("75.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
    )
    assert second.pk != first.pk
    assert Refund.objects.filter(booking=booking).count() == 2


@pytest.mark.django_db
def test_execute__is_idempotent_on_refund_pk(
    booking: Any,
    gbp: Any,
    paid_deposit: Payment,
    user: Any,
    approver: Any,
) -> None:
    """Re-executing the same Refund must not mint a duplicate outbound Payment.

    Once :execute fires, the refund moves to EXECUTING and the gateway
    Payment row is created. A retry (webhook re-delivery, double-click)
    must return the refund as-is and leave the Payment count at one.
    """
    _grant(approver, "approve_refund", "execute_refund", "self_approve_refund")
    refund = RefundService.request(
        booking=booking,
        amount=Decimal("100.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
    )
    RefundService.approve(refund, actor=approver)
    RefundService.execute(refund, actor=approver)
    RefundService.execute(refund, actor=approver)  # retry

    outbound = Payment.objects.filter(
        booking=booking,
        purpose=PaymentPurpose.REFUND.value,
    )
    assert outbound.count() == 1
    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value


@pytest.mark.django_db
def test_from_cancellation__returns_none_when_fee_consumes_paid_total(
    booking: Any,
    property_: Any,
    paid_deposit: Payment,
    user: Any,
) -> None:
    _configure_cancellation(
        property_,
        fee_amount=Decimal("999.00"),
        fee_percent=Decimal("0.00"),
    )
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    refund = RefundService.from_cancellation(
        booking,
        reason="late cancel",
        requested_by=user,
    )
    assert refund is None


@pytest.mark.django_db
def test_refund_service_emits_structured_events(
    booking: Any,
    gbp: Any,
    paid_deposit: Payment,
    user: Any,
    approver: Any,
) -> None:
    """request/execute emit the `refund.request`/`refund.execute` op triples.

    Refund is money movement — losing its structured observability would be a
    silent regression worth catching, so we pin the success lines and the key
    fields (refund_id / amount / outbound_payment_created) that ride on them.
    """
    from structlog.testing import capture_logs

    _grant(approver, "approve_refund", "execute_refund", "self_approve_refund")
    with capture_logs() as logs:
        refund = RefundService.request(
            booking=booking,
            amount=Decimal("100.00"),
            currency=gbp,
            purpose_track=RefundPurposeTrack.DEPOSIT.value,
            reason_code=RefundReasonCode.OVERPAYMENT.value,
            against_payment=paid_deposit,
            requested_by=user,
        )
        RefundService.approve(refund, actor=approver)
        RefundService.execute(refund, actor=approver)

    requested = next(e for e in logs if e["event"] == "refund.request.succeeded")
    assert requested["refund_id"] == refund.pk
    assert requested["amount"] == "100.00"
    assert requested["currency"] == gbp.code

    executed = next(e for e in logs if e["event"] == "refund.execute.succeeded")
    assert executed["refund_id"] == refund.pk
    assert executed["outbound_payment_created"] is True


# ----------------------------------------------------------------------
# Refund completion — EXECUTING → SUCCEEDED / FAILED via the outbound
# Payment's terminal signals (payments-side receivers).
# ----------------------------------------------------------------------


def _executing_refund(
    booking: Any,
    gbp: Any,
    paid_deposit: Payment,
    user: Any,
    approver: Any,
    *,
    method: str = RefundMethod.ONLINE_GATEWAY.value,
) -> Refund:
    _grant(approver, "approve_refund", "execute_refund", "self_approve_refund")
    refund = RefundService.request(
        booking=booking,
        amount=Decimal("100.00"),
        currency=gbp,
        purpose_track=RefundPurposeTrack.DEPOSIT.value,
        reason_code=RefundReasonCode.OVERPAYMENT.value,
        against_payment=paid_deposit,
        requested_by=user,
        method=method,
    )
    RefundService.approve(refund, actor=approver)
    return RefundService.execute(refund, actor=approver)


def _outbound(refund: Refund) -> Payment:
    return Payment.objects.get(
        booking=refund.booking,
        purpose=PaymentPurpose.REFUND.value,
        meta__refund_id=refund.pk,
    )


@pytest.mark.django_db
def test_execute__manual_method_completes_refund(
    booking: Any, gbp: Any, paid_deposit: Payment, user: Any, approver: Any
) -> None:
    refund = _executing_refund(
        booking,
        gbp,
        paid_deposit,
        user,
        approver,
        method=RefundMethod.MANUAL_BANK_TRANSFER.value,
    )

    refund.refresh_from_db()
    assert refund.status == RefundStatus.SUCCEEDED.value
    assert refund.settled_at is not None
    assert _outbound(refund).status == PaymentStatus.SUCCEEDED.value


@pytest.mark.django_db
def test_execute__manual_method_double_execute_is_idempotent(
    booking: Any, gbp: Any, paid_deposit: Payment, user: Any, approver: Any
) -> None:
    refund = _executing_refund(
        booking,
        gbp,
        paid_deposit,
        user,
        approver,
        method=RefundMethod.MANUAL_BANK_TRANSFER.value,
    )
    refund.refresh_from_db()

    RefundService.execute(refund, actor=approver)  # double-click retry

    assert refund.status == RefundStatus.SUCCEEDED.value
    assert Payment.objects.filter(booking=booking, purpose=PaymentPurpose.REFUND.value).count() == 1


@pytest.mark.django_db
def test_execute__gateway_method_stays_executing(
    booking: Any, gbp: Any, paid_deposit: Payment, user: Any, approver: Any
) -> None:
    refund = _executing_refund(booking, gbp, paid_deposit, user, approver)

    refund.refresh_from_db()
    assert refund.status == RefundStatus.EXECUTING.value
    assert _outbound(refund).status == PaymentStatus.PROCESSING.value


@pytest.mark.django_db
def test_outbound_payment_success_advances_refund(
    booking: Any, gbp: Any, paid_deposit: Payment, user: Any, approver: Any
) -> None:
    refund = _executing_refund(booking, gbp, paid_deposit, user, approver)

    _outbound(refund).transition_to(PaymentStatus.SUCCEEDED.value)

    refund.refresh_from_db()
    assert refund.status == RefundStatus.SUCCEEDED.value
    assert refund.settled_at is not None


@pytest.mark.django_db
def test_outbound_payment_failure_marks_refund_failed(
    booking: Any, gbp: Any, paid_deposit: Payment, user: Any, approver: Any
) -> None:
    refund = _executing_refund(booking, gbp, paid_deposit, user, approver)

    _outbound(refund).transition_to(PaymentStatus.FAILED.value, reason="card_expired")

    refund.refresh_from_db()
    assert refund.status == RefundStatus.FAILED.value
    assert refund.failure_reason == "card_expired"


@pytest.mark.django_db
def test_sync_is_idempotent_when_refund_already_terminal(
    booking: Any, gbp: Any, paid_deposit: Payment, user: Any, approver: Any
) -> None:
    refund = _executing_refund(booking, gbp, paid_deposit, user, approver)
    outbound = _outbound(refund)
    outbound.transition_to(PaymentStatus.SUCCEEDED.value)
    refund.refresh_from_db()

    with structlog.testing.capture_logs() as logs:
        RefundService.sync_from_outbound_payment(outbound)

    refund.refresh_from_db()
    assert refund.status == RefundStatus.SUCCEEDED.value
    assert any(e["event"] == "refund.sync_skipped" for e in logs)


@pytest.mark.django_db
def test_normal_payment_refunded_status_does_not_touch_refund_rows(
    booking: Any, gbp: Any, paid_deposit: Payment
) -> None:
    """A DEPOSIT payment reaching REFUNDED fires `payment_refunded` too —
    the sync receiver must ignore non-REFUND-purpose payments."""
    paid_deposit.transition_to(PaymentStatus.REFUNDED.value)

    assert Refund.objects.count() == 0
