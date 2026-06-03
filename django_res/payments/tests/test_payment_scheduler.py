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


@pytest.mark.django_db
def test_create_for_booking__is_idempotent(
    booking: Any,
    property_: Property,
) -> None:
    """A second call returns the existing rows without duplicating them.

    The scheduler is reachable from the `booking_transitioned` signal and from
    explicit callers, so a re-entry (signal re-fire, retry) must be a no-op
    rather than minting a second deposit/balance/SD set.
    """
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
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    first = PaymentScheduler.create_for_booking(booking)
    second = PaymentScheduler.create_for_booking(booking)

    assert {p.pk for p in second} == {p.pk for p in first}
    assert Payment.objects.filter(booking=booking).count() == len(first)
    # The SD row is created once and the retry must not open a second one.
    assert SecurityDeposit.objects.filter(booking=booking).count() == 1


@pytest.mark.django_db
def test_create_for_booking__no_finance_schedules_nothing(
    booking: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A property with no `PropertyFinance` row produces no payments instead of
    raising — the signal fires on every booking, so a financeless property must
    degrade gracefully (matches `Property.balance_due_at`). The skip is logged:
    a missing finance row is a misconfiguration worth surfacing, not swallowing.
    """
    import logging

    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    with caplog.at_level(logging.WARNING, logger="payments.services.payment_scheduler"):
        created = PaymentScheduler.create_for_booking(booking)

    assert created == []
    assert not Payment.objects.filter(booking=booking).exists()
    assert not SecurityDeposit.objects.filter(booking=booking).exists()
    assert any("no PropertyFinance" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_create_for_booking__ignores_unrelated_payments_for_idempotency(
    booking: Any,
    property_: Property,
    gbp: Any,
) -> None:
    """A pre-existing non-schedule Payment must not suppress the schedule.

    The idempotency guard is scoped to DEPOSIT/BALANCE purposes, so an unrelated
    Payment on the booking (e.g. a SECURITY_DEPOSIT hold) does not masquerade as
    'already scheduled' and skip minting the deposit/balance rows.
    """
    _ensure_finance(property_)
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    # An unrelated SECURITY_DEPOSIT payment lands on the booking first.
    Payment.objects.create(
        booking=booking,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
        status=PaymentStatus.SUCCEEDED.value,
        amount=Decimal("500.00"),
        currency=gbp,
        reference="P-SD-EXISTING",
    )

    created = PaymentScheduler.create_for_booking(booking)

    purposes = {p.purpose for p in created}
    assert PaymentPurpose.DEPOSIT.value in purposes
    assert PaymentPurpose.BALANCE.value in purposes
