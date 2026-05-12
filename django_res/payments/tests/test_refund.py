"""Tests for `Refund` workflow + `RefundService`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.db import IntegrityError, transaction

from payments.enums import (
    PaymentPurpose,
    PaymentStatus,
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
