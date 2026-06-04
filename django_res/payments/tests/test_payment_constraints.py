"""Per-purpose active-cardinality constraints on `Payment` (BUG-006).

DEPOSIT / BALANCE / SECURITY_DEPOSIT are single-cardinality (one active row
per booking); CONCIERGE / REFUND are many-per-booking. Each single-cardinality
purpose has its own `UniqueConstraint`; the dangerous one is SECURITY_DEPOSIT —
two active rows would mean two real holds on the guest's card.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from payments.enums import ACTIVE_PAYMENT_STATUSES, PaymentPurpose, PaymentStatus
from payments.models import Payment


@pytest.fixture
def concierge_item(booking: Any, gbp: Any) -> Any:
    from reservations.models import BookingConciergeItem

    return BookingConciergeItem.objects.create(
        booking=booking,
        name="Airport transfer",
        currency=gbp,
    )


def _make(booking: Any, gbp: Any, *, purpose: str, status: str) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=purpose,
        status=status,
        amount=Decimal("100.00"),
        currency=gbp,
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "purpose",
    [
        PaymentPurpose.DEPOSIT.value,
        PaymentPurpose.BALANCE.value,
        PaymentPurpose.SECURITY_DEPOSIT.value,
    ],
)
def test_second_active_single_cardinality_payment_rejected(
    booking: Any, gbp: Any, purpose: str
) -> None:
    _make(booking, gbp, purpose=purpose, status=PaymentStatus.PENDING.value)
    with pytest.raises(IntegrityError), transaction.atomic():
        _make(booking, gbp, purpose=purpose, status=PaymentStatus.SUCCEEDED.value)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "purpose",
    [PaymentPurpose.CONCIERGE.value, PaymentPurpose.REFUND.value],
)
def test_many_active_allowed_for_multi_cardinality_purposes(
    booking: Any, gbp: Any, purpose: str
) -> None:
    _make(booking, gbp, purpose=purpose, status=PaymentStatus.PENDING.value)
    # No constraint → a second active row of the same purpose is fine.
    second = _make(booking, gbp, purpose=purpose, status=PaymentStatus.SUCCEEDED.value)
    assert second.pk is not None


@pytest.mark.django_db
def test_inactive_security_deposit_does_not_block_new_active_one(booking: Any, gbp: Any) -> None:
    """A FAILED/CANCELLED SD frees the slot — a fresh active SD can be created."""
    _make(
        booking,
        gbp,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
        status=PaymentStatus.FAILED.value,
    )
    fresh = _make(
        booking,
        gbp,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
        status=PaymentStatus.PENDING.value,
    )
    assert fresh.pk is not None


def test_active_payment_statuses_membership_is_pinned() -> None:
    """Pin the active-status set: adding a status (e.g. AUTHORISED) must force a
    review of the per-purpose unique constraints, which key off this tuple
    (BUG-006 enum-drift guard)."""
    assert set(ACTIVE_PAYMENT_STATUSES) == {
        PaymentStatus.PENDING.value,
        PaymentStatus.PROCESSING.value,
        PaymentStatus.SUCCEEDED.value,
    }


# ---------------------------------------------------------------------------
# Field-coherence constraints (FG-004): fields that are meaningless for a
# `purpose` must not be populated for that purpose.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_refund_with_due_at_rejected(booking: Any, gbp: Any) -> None:
    """A refund is backward-looking — a `due_at` on it is nonsense."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.create(
            booking=booking,
            purpose=PaymentPurpose.REFUND.value,
            status=PaymentStatus.PROCESSING.value,
            amount=Decimal("50.00"),
            currency=gbp,
            due_at=timezone.now(),
        )


@pytest.mark.django_db
def test_refund_without_due_at_allowed(booking: Any, gbp: Any) -> None:
    refund = _make(
        booking, gbp, purpose=PaymentPurpose.REFUND.value, status=PaymentStatus.PROCESSING.value
    )
    assert refund.due_at is None
    assert refund.pk is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "purpose",
    [
        PaymentPurpose.DEPOSIT.value,
        PaymentPurpose.BALANCE.value,
        PaymentPurpose.SECURITY_DEPOSIT.value,
    ],
)
def test_forward_looking_purposes_may_carry_due_at(booking: Any, gbp: Any, purpose: str) -> None:
    payment = Payment.objects.create(
        booking=booking,
        purpose=purpose,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("100.00"),
        currency=gbp,
        due_at=timezone.now(),
    )
    assert payment.pk is not None


@pytest.mark.django_db
def test_concierge_item_on_non_concierge_payment_rejected(
    booking: Any, gbp: Any, concierge_item: Any
) -> None:
    """`concierge_item` only attaches to a CONCIERGE row."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.create(
            booking=booking,
            purpose=PaymentPurpose.DEPOSIT.value,
            status=PaymentStatus.PENDING.value,
            amount=Decimal("100.00"),
            currency=gbp,
            concierge_item=concierge_item,
        )


@pytest.mark.django_db
def test_concierge_item_on_concierge_payment_allowed(
    booking: Any, gbp: Any, concierge_item: Any
) -> None:
    payment = Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.CONCIERGE.value,
        status=PaymentStatus.PENDING.value,
        amount=Decimal("100.00"),
        currency=gbp,
        concierge_item=concierge_item,
    )
    assert payment.pk is not None


@pytest.mark.django_db
def test_negative_refund_amount_rejected(booking: Any, gbp: Any) -> None:
    """INV-003: refund amounts are recorded positive; `purpose` tags direction."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.create(
            booking=booking,
            purpose=PaymentPurpose.REFUND.value,
            status=PaymentStatus.PROCESSING.value,
            amount=Decimal("-50.00"),
            currency=gbp,
        )
