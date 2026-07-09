"""Tests for `payments.services.PaymentScheduler`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from payments.enums import PaymentPurpose, PaymentStatus, SecurityDepositStatus
from payments.models import Payment, SecurityDeposit
from payments.services import PaymentScheduler
from properties.models import Property
from properties.models.finance import PropertyFinance


def _ensure_finance(property_: Property) -> PropertyFinance:
    """Build the per-property finance row (policy lives on it, GAP-070)."""
    finance, _ = PropertyFinance.objects.get_or_create(property=property_)
    return finance


@pytest.mark.django_db
def test_create_for_booking__creates_deposit_balance_and_security_deposit(
    booking: Any,
    property_: Property,
) -> None:
    finance = _ensure_finance(property_)
    finance.security_deposit_required = True
    finance.security_deposit_amount = Decimal("500.00")
    finance.security_deposit_calculation_type = "fixed"
    finance.save(
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
def test_create_for_booking__deposit_plus_balance_conserves_total(
    booking: Any,
    property_: Property,
) -> None:
    """deposit_saved + balance_saved == total for a percentage-split deposit.

    Regression for the SMELL-003 follow-up: the BALANCE row must subtract the
    *quantised* deposit, so money is conserved by construction. For a 2dp
    currency (GBP, 30% of 1400) this is a no-op — the existing 420/980 split
    already conserves — but it pins the invariant.
    """
    _ensure_finance(property_)
    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    created = PaymentScheduler.create_for_booking(booking)
    total = booking.balance_due
    deposit = next(p for p in created if p.purpose == PaymentPurpose.DEPOSIT.value)
    balance = next(p for p in created if p.purpose == PaymentPurpose.BALANCE.value)

    assert deposit.amount + balance.amount == total
    assert deposit.amount == Decimal("420.00")
    assert balance.amount == Decimal("980.00")


@pytest.mark.django_db
def test_create_for_booking__gap079_deposit_and_balance_reconcile_engine_total(
    booking: Any,
    property_: Property,
) -> None:
    """GAP-079 acceptance: the commission-after-local-VAT worked example
    reconciles end-to-end for BOTH deposit and balance.

    The engine prices a GROSS 13%-VAT / 20%-commission villa (10,000 over
    8 nights — see the pins in `pricing/tests/test_engine_price_basis.py`);
    its breakdown becomes the booking snapshot, and the scheduler splits the
    engine total (the guest-facing gross, out of which VAT and commission
    were carved) 30/70. Owner money is derived upstream by the engine, not
    by the schedule.
    """
    from datetime import timedelta

    from pricing.models import RateBand, RatePeriod, RatePlan
    from pricing.services import PricingEngine
    from reservations.models import Booking

    finance = _ensure_finance(property_)
    finance.commission_calculation_type = "percent"
    finance.commission_amount = Decimal("20")
    finance.tax_percentage = Decimal("13")
    finance.tax_is_exempt = False
    # Deposit fields stay NULL → 30% PERCENT policy floor.
    finance.save(
        update_fields=[
            "commission_calculation_type",
            "commission_amount",
            "tax_percentage",
            "tax_is_exempt",
        ]
    )

    stay_from = booking.date_from
    stay_to = stay_from + timedelta(days=8)  # 8 x 1,250.00 = exactly 10,000
    plan = RatePlan.objects.create(
        property=property_,
        name="GAP-079",
        currency=booking.currency,
        effective_from=stay_from - timedelta(days=30),
        effective_to=stay_to + timedelta(days=30),
    )
    period = RatePeriod.objects.create(plan=plan, name="Stay", date_from=stay_from, date_to=stay_to)
    RateBand.objects.create(period=period, min_party=1, max_party=8, nightly=Decimal("1250.00"))

    quote = PricingEngine.quote(
        property=property_,
        date_from=stay_from,
        date_to=stay_to,
        party=2,
        currency=booking.currency,
    )
    # The engine-derived worked example (13% VAT first, then 20% commission).
    assert quote.breakdown["total"] == "10000.00"
    assert quote.breakdown["tax"] == "1300.00"
    assert quote.breakdown["commission"] == "1740.00"
    assert quote.breakdown["net_to_owner"] == "6960.00"

    # The scheduler reads only the snapshot total; date_to/balance_due are
    # updated so the booking rows stay coherent with the priced stay.
    booking.date_to = stay_to
    booking.pricing_snapshot = quote.breakdown
    booking.balance_due = quote.total
    booking.save(update_fields=["date_to", "pricing_snapshot", "balance_due"])
    # Re-fetch so the property's cached `.finance` reflects the new row.
    booking = Booking.objects.get(pk=booking.pk)

    created = PaymentScheduler.create_for_booking(booking)

    deposit = next(p for p in created if p.purpose == PaymentPurpose.DEPOSIT.value)
    balance = next(p for p in created if p.purpose == PaymentPurpose.BALANCE.value)
    assert deposit.amount == Decimal("3000.00")  # 30% of the engine total
    assert balance.amount == Decimal("7000.00")
    assert deposit.amount + balance.amount == Decimal("10000.00")


@pytest.mark.django_db
def test_create_for_booking__conserves_total_for_zero_dp_currency(
    booking: Any,
    property_: Property,
) -> None:
    """A 0dp currency at an exact-half split still conserves the total.

    Total 1 JPY, 50% deposit → 0.5 rounds HALF_EVEN to 0; the balance must
    derive from the quantised 0 (→ 1), so deposit + balance == 1. The pre-fix
    code subtracted the *unquantised* 0.5, quantising 0.5 → 0 and losing the
    whole total.
    """
    from pricing.models import Currency
    from reservations.models import Booking

    jpy = Currency.objects.create(code="JPY", name="Japanese yen", symbol="¥", decimal_places=0)
    finance = _ensure_finance(property_)
    finance.deposit_required = True
    finance.deposit_calculation_type = "percent"
    finance.deposit_amount = Decimal("50")
    finance.save(
        update_fields=[
            "deposit_required",
            "deposit_calculation_type",
            "deposit_amount",
        ]
    )

    booking = Booking.objects.get(pk=booking.pk)
    booking.currency = jpy
    booking.balance_due = Decimal("1")
    booking.rental_price = Decimal("1")
    booking.pricing_snapshot = {"total": "1"}
    booking.save(update_fields=["currency", "balance_due", "rental_price", "pricing_snapshot"])

    created = PaymentScheduler.create_for_booking(booking)
    deposit = next(p for p in created if p.purpose == PaymentPurpose.DEPOSIT.value)
    balance = next(p for p in created if p.purpose == PaymentPurpose.BALANCE.value)

    assert deposit.amount + balance.amount == Decimal("1")


@pytest.mark.django_db
def test_create_for_booking__skips_security_deposit_when_not_required(
    booking: Any,
    property_: Property,
) -> None:
    finance = _ensure_finance(property_)
    finance.security_deposit_required = False
    finance.save(update_fields=["security_deposit_required"])
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
    finance = _ensure_finance(property_)
    finance.security_deposit_required = True
    finance.security_deposit_amount = Decimal("500.00")
    finance.security_deposit_calculation_type = "fixed"
    finance.save(
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
) -> None:
    """A property with no `PropertyFinance` row produces no payments instead of
    raising — the signal fires on every booking, so a financeless property must
    degrade gracefully (matches `Property.balance_due_at`). The skip is logged:
    a missing finance row is a misconfiguration worth surfacing, not swallowing.
    """
    from structlog.testing import capture_logs

    from reservations.models import Booking

    booking = Booking.objects.get(pk=booking.pk)

    with capture_logs() as logs:
        created = PaymentScheduler.create_for_booking(booking)

    assert created == []
    assert not Payment.objects.filter(booking=booking).exists()
    assert not SecurityDeposit.objects.filter(booking=booking).exists()
    skip = next(e for e in logs if e["event"] == "payment.schedule_skipped")
    assert skip["reason"] == "no_property_finance"
    assert skip["booking_id"] == booking.pk


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
