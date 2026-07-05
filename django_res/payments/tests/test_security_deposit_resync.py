"""Tests for `SecurityDepositService.resize_for_booking` — GAP-019 part 2.

A charge (or modify) that moves the booking total *after* the SD row exists
must resize the SD too — `PaymentScheduler.resync_for_booking` deliberately
filters to DEPOSIT/BALANCE, so without this the SD only tracked charges that
existed at creation time. The resize is safe only while the SD is still
pre-charge (AWAITING_DETAILS / AWAITING_BT); once it is PRE_AUTHED / HELD the
figure is committed at the provider and must not be silently changed.

These exercise the real `booking_total_changed` receiver path (adding a charge
fires the signal), so they pin both the service and its wiring.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from payments.enums import SecurityDepositStatus
from payments.models.payment_event import PaymentEvent
from payments.services.security_deposit import SecurityDepositService
from reservations.models import Booking, BookingChargeItem


def _percent_sd_finance(property_: Any, *, method: str = "card_hold") -> None:
    """Give `property_` a 10%-of-total security-deposit policy."""
    from properties.models.finance import PropertyFinance

    finance, _ = PropertyFinance.objects.get_or_create(property=property_)
    finance.security_deposit_required = True
    finance.security_deposit_amount = Decimal("10.00")
    finance.security_deposit_calculation_type = "percent"
    finance.security_deposit_payment_method = method
    finance.save(
        update_fields=[
            "security_deposit_required",
            "security_deposit_amount",
            "security_deposit_calculation_type",
            "security_deposit_payment_method",
        ]
    )


def _add_charge(booking: Booking, amount: str) -> BookingChargeItem:
    return BookingChargeItem.objects.create(
        booking=booking, label="Extra", amount=Decimal(amount), currency=booking.currency
    )


@pytest.mark.django_db
def test_charge_after_sd_resizes_while_awaiting_details(booking: Any, property_: Any) -> None:
    """A charge added after the SD exists resizes it — closes the gap where the
    fix only helped charges present at creation time. 10% of 1400 = 140;
    +600 charge → 10% of 2000 = 200, via the signal alone (no explicit call)."""
    _percent_sd_finance(property_, method="card_hold")
    booking = Booking.objects.get(pk=booking.pk)
    sd = SecurityDepositService.create_for_booking(booking)
    assert sd is not None
    assert sd.status == SecurityDepositStatus.AWAITING_DETAILS.value
    assert sd.amount == Decimal("140.00")

    _add_charge(booking, "600.00")

    sd.refresh_from_db()
    assert sd.amount == Decimal("200.00")


@pytest.mark.django_db
def test_charge_resizes_while_awaiting_bt(booking: Any, property_: Any) -> None:
    """The BT-refundable pre-charge state (AWAITING_BT) resizes too."""
    _percent_sd_finance(property_, method="bank_transfer")
    booking = Booking.objects.get(pk=booking.pk)
    sd = SecurityDepositService.create_for_booking(booking)
    assert sd is not None
    assert sd.status == SecurityDepositStatus.AWAITING_BT.value
    assert sd.amount == Decimal("140.00")

    _add_charge(booking, "600.00")

    sd.refresh_from_db()
    assert sd.amount == Decimal("200.00")


@pytest.mark.django_db
def test_no_resize_once_pre_authed_and_skip_event_written(booking: Any, property_: Any) -> None:
    """A PRE_AUTHED SD is committed at the provider — the figure is frozen and a
    single deliberate skip event records the un-applied total change for
    operators.

    Drives the SD through the real `hold()` transition (not a bulk `.update()`)
    so it reaches PRE_AUTHED the way production does, and asserts exactly one
    skip event so a re-introduced over-fire would be caught."""
    _percent_sd_finance(property_, method="card_hold")
    booking = Booking.objects.get(pk=booking.pk)
    sd = SecurityDepositService.create_for_booking(booking)
    assert sd is not None
    SecurityDepositService.hold(sd, gateway_response={"provider_reference": "pi_test"})
    sd.refresh_from_db()
    assert sd.status == SecurityDepositStatus.PRE_AUTHED.value

    _add_charge(booking, "600.00")

    sd.refresh_from_db()
    assert sd.amount == Decimal("140.00")
    skips = PaymentEvent.objects.filter(security_deposit=sd, kind="RESIZE_SKIPPED")
    assert skips.count() == 1
    skip = skips.get()
    assert skip.meta["status"] == SecurityDepositStatus.PRE_AUTHED.value
    assert skip.meta["would_be"] == "200.00"


@pytest.mark.django_db
def test_no_skip_event_when_figure_unchanged(booking: Any, property_: Any) -> None:
    """A signal that leaves the SD figure unchanged writes no event at all —
    even past the pre-charge window. Pins the fix for the skip-event over-fire
    where every `booking_total_changed` on a PRE_AUTHED/fixed SD wrote a
    RESIZE_SKIPPED row regardless of whether the figure actually moved."""
    from properties.models.finance import PropertyFinance

    finance, _ = PropertyFinance.objects.get_or_create(property=property_)
    finance.security_deposit_required = True
    finance.security_deposit_amount = Decimal("500.00")
    finance.security_deposit_calculation_type = "fixed"
    finance.security_deposit_payment_method = "card_hold"
    finance.save(
        update_fields=[
            "security_deposit_required",
            "security_deposit_amount",
            "security_deposit_calculation_type",
            "security_deposit_payment_method",
        ]
    )
    booking = Booking.objects.get(pk=booking.pk)
    sd = SecurityDepositService.create_for_booking(booking)
    assert sd is not None
    SecurityDepositService.hold(sd, gateway_response={"provider_reference": "pi_test"})
    sd.refresh_from_db()
    assert sd.status == SecurityDepositStatus.PRE_AUTHED.value

    _add_charge(booking, "600.00")

    sd.refresh_from_db()
    assert sd.amount == Decimal("500.00")
    assert not PaymentEvent.objects.filter(
        security_deposit=sd, kind__in=("RESIZE", "RESIZE_SKIPPED")
    ).exists()


@pytest.mark.django_db
def test_negative_charge_shrinks_pre_charge_sd(booking: Any, property_: Any) -> None:
    """A credit charge that lowers the total shrinks a still-pre-charge SD.

    This is the GAP-016 signed-charge-line case (a "Negotiated rate adjustment"
    line goes in negative) and the only path that exercises the *down*
    direction — without it the resize is only ever tested growing."""
    _percent_sd_finance(property_, method="card_hold")
    booking = Booking.objects.get(pk=booking.pk)
    sd = SecurityDepositService.create_for_booking(booking)
    assert sd is not None
    assert sd.amount == Decimal("140.00")

    _add_charge(booking, "600.00")  # total 1400 → 2000, SD 200
    sd.refresh_from_db()
    assert sd.amount == Decimal("200.00")

    _add_charge(booking, "-1000.00")  # total 2000 → 1000, SD 100
    sd.refresh_from_db()
    assert sd.amount == Decimal("100.00")

    event = PaymentEvent.objects.filter(security_deposit=sd, kind="RESIZE").latest("created_at")
    assert event.meta["from_amount"] == "200.00"
    assert event.meta["to_amount"] == "100.00"


@pytest.mark.django_db
def test_non_positive_total_keeps_amount_and_records_skip(booking: Any, property_: Any) -> None:
    """A credit that drives the recomputed figure to <= 0 cannot be written (the
    amount>0 constraint), so the SD stays at its current figure — but a skip
    event records that it is now overstated, rather than the resize returning
    mute (mirrors the schedule resync's residual bookkeeping)."""
    _percent_sd_finance(property_, method="card_hold")
    booking = Booking.objects.get(pk=booking.pk)
    sd = SecurityDepositService.create_for_booking(booking)
    assert sd is not None
    assert sd.amount == Decimal("140.00")

    _add_charge(booking, "-1400.00")  # total 1400 → 0, SD would be 0

    sd.refresh_from_db()
    assert sd.amount == Decimal("140.00")  # unchanged — 0 is not writable
    skip = PaymentEvent.objects.filter(security_deposit=sd, kind="RESIZE_SKIPPED").latest(
        "created_at"
    )
    assert skip.meta["reason"] == "non_positive_total"
    assert skip.meta["would_be"] == "0.00"


@pytest.mark.django_db
def test_resize_writes_audit_event_on_change(booking: Any, property_: Any) -> None:
    """A successful resize leaves an audit trail on the SD timeline."""
    _percent_sd_finance(property_, method="card_hold")
    booking = Booking.objects.get(pk=booking.pk)
    sd = SecurityDepositService.create_for_booking(booking)
    assert sd is not None

    _add_charge(booking, "600.00")

    event = PaymentEvent.objects.filter(security_deposit=sd, kind="RESIZE").latest("created_at")
    assert event.meta["from_amount"] == "140.00"
    assert event.meta["to_amount"] == "200.00"


@pytest.mark.django_db
def test_fixed_sd_is_unaffected_by_total_change(booking: Any, property_: Any) -> None:
    """A fixed SD doesn't depend on the total — a charge leaves it untouched and
    writes no spurious resize event."""
    from properties.models.finance import PropertyFinance

    finance, _ = PropertyFinance.objects.get_or_create(property=property_)
    finance.security_deposit_required = True
    finance.security_deposit_amount = Decimal("500.00")
    finance.security_deposit_calculation_type = "fixed"
    finance.security_deposit_payment_method = "card_hold"
    finance.save(
        update_fields=[
            "security_deposit_required",
            "security_deposit_amount",
            "security_deposit_calculation_type",
            "security_deposit_payment_method",
        ]
    )
    booking = Booking.objects.get(pk=booking.pk)
    sd = SecurityDepositService.create_for_booking(booking)
    assert sd is not None
    assert sd.amount == Decimal("500.00")

    _add_charge(booking, "600.00")

    sd.refresh_from_db()
    assert sd.amount == Decimal("500.00")
    assert not PaymentEvent.objects.filter(security_deposit=sd, kind="RESIZE").exists()


@pytest.mark.django_db
def test_resize_for_booking_no_sd_is_noop(booking: Any, property_: Any) -> None:
    """No SD on the booking → the resize returns None and raises nothing."""
    from properties.models.finance import PropertyFinance

    PropertyFinance.objects.get_or_create(property=property_)
    booking = Booking.objects.get(pk=booking.pk)

    assert SecurityDepositService.resize_for_booking(booking) is None
