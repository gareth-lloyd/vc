"""Tests for `payments.services.PaymentScheduler`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from payments.enums import PaymentPurpose, PaymentStatus, SecurityDepositStatus
from payments.models import Payment, SecurityDeposit
from payments.services import PaymentScheduler
from properties.models import Property
from properties.models.finance import GroupFinance, PropertyFinance


def _ensure_finance(property_: Property) -> GroupFinance:
    """Build both `GroupFinance` and the per-property override row."""
    gf, _ = GroupFinance.objects.get_or_create(group=property_.group)
    PropertyFinance.objects.get_or_create(property=property_)
    return gf


@pytest.mark.django_db
def test_create_for_booking__creates_deposit_balance_and_security_deposit(
    booking: Any,
    property_: Property,
) -> None:
    gf = _ensure_finance(property_)
    gf.security_deposit_required = True
    gf.security_deposit_amount = Decimal("500.00")
    gf.security_deposit_calculation_type = "fixed"
    gf.save(
        update_fields=[
            "security_deposit_required",
            "security_deposit_amount",
            "security_deposit_calculation_type",
        ]
    )
    # Re-fetch so the property's cached `.finance` reflects the new row.
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    created = PaymentScheduler.create_for_booking(booking)

    purposes = {p.purpose for p in created}
    assert PaymentPurpose.DEPOSIT.value in purposes
    assert PaymentPurpose.BALANCE.value in purposes
    for p in created:
        assert p.status == PaymentStatus.PENDING.value
        assert p.reference.startswith("P-")

    deposit = next(p for p in created if p.purpose == PaymentPurpose.DEPOSIT.value)
    assert deposit.amount == Decimal("420.00")  # 30% of 1400

    balance = next(p for p in created if p.purpose == PaymentPurpose.BALANCE.value)
    assert balance.amount == Decimal("980.00")

    sd = SecurityDeposit.objects.get(booking=booking)
    assert sd.amount == Decimal("500.00")
    assert sd.status == SecurityDepositStatus.AWAITING_DETAILS.value


@pytest.mark.django_db
def test_create_for_booking__skips_security_deposit_when_not_required(
    booking: Any,
    property_: Property,
) -> None:
    gf = _ensure_finance(property_)
    gf.security_deposit_required = False
    gf.save(update_fields=["security_deposit_required"])
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    PaymentScheduler.create_for_booking(booking)

    assert not SecurityDeposit.objects.filter(booking=booking).exists()
    assert Payment.objects.filter(booking=booking).count() == 2
