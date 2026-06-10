"""Tests for the `SecurityDeposit` workflow + `SecurityDepositService`."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from payments.enums import (
    PaymentMethod,
    PaymentPurpose,
    PaymentStatus,
    SecurityDepositKind,
    SecurityDepositStatus,
)
from payments.models import Payment, SecurityDeposit
from payments.services.security_deposit import SecurityDepositService


@pytest.mark.django_db
def test_create_for_booking__is_idempotent(booking: Any, property_: Any) -> None:
    """A second `create_for_booking` returns the existing SD, never a duplicate.

    `create_for_booking` is reachable from the booking-creation signal and the
    scheduler, so a re-entry must short-circuit — two active SECURITY_DEPOSIT
    rows per booking would break the one-active-per-booking invariant (BUG-006).
    """
    from decimal import Decimal

    from properties.models.finance import GroupFinance, PropertyFinance

    gf, _ = GroupFinance.objects.get_or_create(group=property_.group)
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
    PropertyFinance.objects.get_or_create(property=property_)
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    first = SecurityDepositService.create_for_booking(booking)
    second = SecurityDepositService.create_for_booking(booking)

    assert first is not None
    assert second is not None
    assert second.pk == first.pk
    assert SecurityDeposit.objects.filter(booking=booking).count() == 1


@pytest.mark.django_db
def test_create_for_booking__percent_base_includes_charge_items(
    booking: Any, property_: Any, gbp: Any
) -> None:
    """A percent SD sizes against the same charges-inclusive total the
    deposit/balance schedule uses — not bare `balance_due`. 10% of
    (1400 + 200) = 160, not 140.
    """
    from properties.models.finance import GroupFinance, PropertyFinance
    from reservations.models import Booking, BookingChargeItem

    gf, _ = GroupFinance.objects.get_or_create(group=property_.group)
    gf.security_deposit_required = True
    gf.security_deposit_amount = Decimal("10.00")
    gf.security_deposit_calculation_type = "percent"
    gf.save(
        update_fields=[
            "security_deposit_required",
            "security_deposit_amount",
            "security_deposit_calculation_type",
        ]
    )
    PropertyFinance.objects.get_or_create(property=property_)
    booking = Booking.objects.get(pk=booking.pk)
    BookingChargeItem.objects.create(
        booking=booking, label="Heating", amount=Decimal("200.00"), currency=gbp
    )

    sd = SecurityDepositService.create_for_booking(booking)

    assert sd is not None
    assert sd.amount == Decimal("160.00")


@pytest.fixture
def pre_auth_sd(db: None, booking: Any, gbp: Any) -> SecurityDeposit:
    return SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.PRE_AUTH_HOLD.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.AWAITING_DETAILS.value,
    )


@pytest.fixture
def bt_sd(db: None, booking: Any, gbp: Any) -> SecurityDeposit:
    return SecurityDeposit.objects.create(
        booking=booking,
        kind=SecurityDepositKind.BT_REFUNDABLE.value,
        amount=Decimal("500.00"),
        currency=gbp,
        status=SecurityDepositStatus.AWAITING_BT.value,
    )


@pytest.mark.django_db
def test_pre_auth_path__hold_release(
    pre_auth_sd: SecurityDeposit,
    booking: Any,
) -> None:
    SecurityDepositService.hold(
        pre_auth_sd,
        gateway_response={
            "provider": "flywire",
            "provider_reference": "flw-123",
            "hold_expires_at": datetime(2026, 8, 1, tzinfo=UTC),
        },
        actor=None,
    )
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.PRE_AUTHED.value
    assert pre_auth_sd.hold_expires_at is not None

    # `:hold` mints a Payment(SECURITY_DEPOSIT, SUCCEEDED).
    payment = Payment.objects.get(
        booking=booking,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
    )
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.meta == {"security_deposit_id": pre_auth_sd.pk, "kind": "PRE_AUTH_HOLD"}

    SecurityDepositService.release(pre_auth_sd, actor=None)
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.RELEASED.value
    assert pre_auth_sd.released_at is not None


@pytest.mark.django_db
def test_pre_auth_path__claim_captures(
    pre_auth_sd: SecurityDeposit,
) -> None:
    SecurityDepositService.hold(
        pre_auth_sd,
        gateway_response={"provider": "flywire"},
        actor=None,
    )
    SecurityDepositService.claim(
        pre_auth_sd,
        damage_claim=42,  # placeholder for the future DamageClaim FK
        captured_amount=Decimal("250.00"),
        actor=None,
    )
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.CAPTURED.value
    assert pre_auth_sd.captured_amount == Decimal("250.00")
    assert pre_auth_sd.damage_claim_id == 42


@pytest.mark.django_db
def test_pre_auth_path__expiry_transition(
    pre_auth_sd: SecurityDeposit,
) -> None:
    SecurityDepositService.hold(
        pre_auth_sd,
        gateway_response={"provider": "flywire"},
        actor=None,
    )
    SecurityDepositService.expire(pre_auth_sd, actor=None)
    pre_auth_sd.refresh_from_db()
    assert pre_auth_sd.status == SecurityDepositStatus.EXPIRED.value


@pytest.mark.django_db
def test_bt_path__mark_paid_then_release(
    bt_sd: SecurityDeposit,
    booking: Any,
) -> None:
    SecurityDepositService.mark_paid(
        bt_sd,
        amount=Decimal("500.00"),
        paid_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        method=PaymentMethod.BANK_TRANSFER.value,
        reference="wire-001",
        actor=None,
    )
    bt_sd.refresh_from_db()
    assert bt_sd.status == SecurityDepositStatus.HELD.value

    payment = Payment.objects.get(
        booking=booking,
        purpose=PaymentPurpose.SECURITY_DEPOSIT.value,
    )
    assert payment.status == PaymentStatus.SUCCEEDED.value
    assert payment.provider_reference == "wire-001"

    SecurityDepositService.release(bt_sd, actor=None)
    bt_sd.refresh_from_db()
    assert bt_sd.status == SecurityDepositStatus.REFUNDED.value
    assert bt_sd.refunded_amount == Decimal("500.00")
