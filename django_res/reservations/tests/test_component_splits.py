"""Tests for `payment_component_splits` — GAP-077 per-component owner money.

The split is derive-on-read: whole-booking owner money
(`owner_money_for_booking`) allocated pro-rata across the booking's
DEPOSIT/BALANCE schedule components, residual cent to the last component
(mirroring the scheduler's odd-cent-to-BALANCE convention). Nothing is
stored — a re-price rewrites the snapshot and resyncs the schedule, and the
split follows.

Test scaffolding may import `payments` (the layers contract ignores
`*.tests.**`); the service itself must not.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from django.utils import timezone

from payments.enums import PaymentStatus
from payments.models import Payment
from properties.models import PropertyFinance
from reservations.services.owner_finance import (
    allocate_proportionally,
    payment_component_splits,
)

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import Booking, TermsVersion


@pytest.fixture
def booking(
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    """Canonical occupying booking (LEAD BookingGuest invariant included);
    dates match the conftest rate fixtures (7 nights x 200 = 1,400)."""
    from reservations.factories import make_occupying_booking

    return make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )


def _finance(property_: Property, **fields: Any) -> PropertyFinance:
    finance, _ = PropertyFinance.objects.get_or_create(property=property_)
    for name, value in fields.items():
        setattr(finance, name, value)
    if fields:
        finance.save(update_fields=list(fields))
    return finance


def _payment(
    booking: Booking,
    *,
    purpose: str,
    amount: str,
    status: str = PaymentStatus.PENDING.value,
    due_at: Any = None,
) -> Payment:
    return Payment.objects.create(
        booking=booking,
        purpose=purpose,
        status=status,
        amount=Decimal(amount),
        currency=booking.currency,
        due_at=due_at,
    )


GAP079_SNAPSHOT = {
    "total": "10000.00",
    "commission": "1740.00",
    "tax": "1300.00",
    "net_to_owner": "6960.00",
    "price_basis": "gross",
}


def _set_snapshot(booking: Booking, snapshot: dict[str, Any]) -> Booking:
    booking.pricing_snapshot = snapshot
    booking.balance_due = Decimal(str(snapshot.get("total", booking.balance_due)))
    booking.save(update_fields=["pricing_snapshot", "balance_due"])
    return booking


# ----------------------------------------------------------------------
# allocate_proportionally — pure helper
# ----------------------------------------------------------------------
def test_allocate_proportionally__residual_cent_lands_on_last_component() -> None:
    """Equal grosses, 0.05 commission: naive per-component quantize gives
    0.02 + 0.02 = 0.04 and loses a cent; residual-to-last conserves it."""
    allocations = allocate_proportionally(
        commission=Decimal("0.05"),
        tax=Decimal("0.03"),
        grosses=[Decimal("1000.00"), Decimal("1000.00")],
    )
    assert allocations == [
        (Decimal("0.02"), Decimal("0.02")),  # half-even: 0.025 → 0.02, 0.015 → 0.02
        (Decimal("0.03"), Decimal("0.01")),
    ]
    assert sum(c for c, _ in allocations) == Decimal("0.05")
    assert sum(t for _, t in allocations) == Decimal("0.03")


def test_allocate_proportionally__three_components() -> None:
    """A future INTERIM slots in with zero rework — N components conserve."""
    allocations = allocate_proportionally(
        commission=Decimal("0.10"),
        tax=Decimal("0.10"),
        grosses=[Decimal("1"), Decimal("1"), Decimal("1")],
    )
    assert allocations == [
        (Decimal("0.03"), Decimal("0.03")),
        (Decimal("0.03"), Decimal("0.03")),
        (Decimal("0.04"), Decimal("0.04")),
    ]


def test_allocate_proportionally__zero_gross_schedule_allocates_nothing() -> None:
    allocations = allocate_proportionally(
        commission=Decimal("100.00"),
        tax=Decimal("50.00"),
        grosses=[Decimal("0.00"), Decimal("0.00")],
    )
    assert allocations == [
        (Decimal("0.00"), Decimal("0.00")),
        (Decimal("0.00"), Decimal("0.00")),
    ]


# ----------------------------------------------------------------------
# payment_component_splits — the GAP-079 worked example
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_splits__gap079_worked_example(booking: Booking, property_: Property) -> None:
    """GROSS 13%-VAT / 20%-commission villa, 10,000 split 30/70.

    Deposit 3,000 → 522 commission / 390 tax / 2,088 net; balance 7,000 →
    1,218 / 910 / 4,872. Sums reproduce the whole-booking 1,740 / 1,300 /
    6,960 exactly (the 30/70 split divides exactly — rounding is pinned
    separately).
    """
    _finance(property_)
    _set_snapshot(booking, GAP079_SNAPSHOT)
    deposit_due = timezone.now()
    balance_due = timezone.now() + timedelta(days=30)
    _payment(booking, purpose="deposit", amount="3000.00", due_at=deposit_due)
    _payment(booking, purpose="balance", amount="7000.00", due_at=balance_due)

    splits = payment_component_splits(booking)

    assert splits is not None
    assert [s["purpose"] for s in splits] == ["deposit", "balance"]
    deposit, balance = splits
    assert deposit["gross"] == Decimal("3000.00")
    assert deposit["commission"] == Decimal("522.00")
    assert deposit["tax"] == Decimal("390.00")
    assert deposit["net_to_owner"] == Decimal("2088.00")
    assert deposit["status"] == "pending"
    assert deposit["due_at"] == deposit_due
    assert balance["gross"] == Decimal("7000.00")
    assert balance["commission"] == Decimal("1218.00")
    assert balance["tax"] == Decimal("910.00")
    assert balance["net_to_owner"] == Decimal("4872.00")
    assert balance["due_at"] == balance_due
    assert sum(s["commission"] for s in splits) == Decimal("1740.00")
    assert sum(s["tax"] for s in splits) == Decimal("1300.00")
    assert sum(s["net_to_owner"] for s in splits) == Decimal("6960.00")


@pytest.mark.django_db
def test_splits__rounding_residual_absorbed_by_balance(
    booking: Booking, property_: Property
) -> None:
    """An uneven (1/3) deposit leaves a quantization cent — BALANCE absorbs
    it and the sums stay exact."""
    _finance(property_)
    _set_snapshot(
        booking,
        {"total": "1000.00", "commission": "100.00", "tax": "50.00", "net_to_owner": "850.00"},
    )
    _payment(booking, purpose="deposit", amount="333.33")
    _payment(booking, purpose="balance", amount="666.67")

    splits = payment_component_splits(booking)

    assert splits is not None
    deposit, balance = splits
    # 100 x 333.33/1000 = 33.333 → 33.33; balance takes 66.67 (not 66.667→66.67
    # by luck — by residual construction).
    assert deposit["commission"] == Decimal("33.33")
    assert balance["commission"] == Decimal("66.67")
    assert deposit["tax"] == Decimal("16.67")  # 16.6665 → 16.67
    assert balance["tax"] == Decimal("33.33")
    assert sum(s["commission"] for s in splits) == Decimal("100.00")
    assert sum(s["tax"] for s in splits) == Decimal("50.00")
    assert sum(s["net_to_owner"] for s in splits) == Decimal("850.00")
    for s in splits:
        assert s["net_to_owner"] == s["gross"] - s["commission"] - s["tax"]


# ----------------------------------------------------------------------
# Non-commissionable extras (GAP-076) — engine-driven, both bases
# ----------------------------------------------------------------------
def _make_noncomm_extra(property_: Property, gbp: Currency) -> None:
    from pricing.enums import ExtraCalc, ExtraKind
    from pricing.models import Extra

    Extra.objects.create(
        property=property_,
        name="Pool heating",
        kind=ExtraKind.HEATING.value,
        calc=ExtraCalc.FIXED_PER_STAY.value,
        amount=Decimal("100.00"),
        currency=gbp,
        is_mandatory=True,
        commissionable=False,
    )


@pytest.mark.django_db
def test_splits__non_commissionable_extra_gross_basis(
    booking: Booking,
    property_: Property,
    gbp: Currency,
    rate_rule: Any,
) -> None:
    """The pass-through extra inflates both components' gross pro-rata; the
    commission/tax totals allocated are unchanged by it (GAP-076 smearing)."""
    from pricing.services import PricingEngine

    _finance(
        property_,
        commission_calculation_type="percent",
        commission_amount=Decimal("20"),
        tax_percentage=Decimal("13"),
        tax_is_exempt=False,
    )
    _make_noncomm_extra(property_, gbp)

    quote = PricingEngine.quote(
        property=property_,
        date_from=booking.date_from,
        date_to=booking.date_to,
        party=2,
        currency=gbp,
    )
    # 7 x 200 = 1,400 commissionable; +100 pass-through = 1,500 guest total.
    assert quote.breakdown["total"] == "1500.00"
    assert quote.breakdown["tax"] == "182.00"  # 13% of 1,400 only
    assert quote.breakdown["commission"] == "243.60"  # 20% of (1,400 - 182)
    assert quote.breakdown["net_to_owner"] == "1074.40"  # 974.40 + 100 pass-through

    _set_snapshot(booking, quote.breakdown)
    _payment(booking, purpose="deposit", amount="450.00")  # 30% of 1,500
    _payment(booking, purpose="balance", amount="1050.00")

    splits = payment_component_splits(booking)

    assert splits is not None
    deposit, balance = splits
    assert deposit["commission"] == Decimal("73.08")  # 243.60 x 0.3
    assert deposit["tax"] == Decimal("54.60")
    assert deposit["net_to_owner"] == Decimal("322.32")
    assert balance["commission"] == Decimal("170.52")
    assert balance["tax"] == Decimal("127.40")
    assert balance["net_to_owner"] == Decimal("752.08")
    assert sum(s["net_to_owner"] for s in splits) == Decimal("1074.40")


@pytest.mark.django_db
def test_splits__non_commissionable_extra_net_basis(
    booking: Booking,
    property_: Property,
    gbp: Currency,
    plan: Any,
    rate_rule: Any,
) -> None:
    """Same acceptance on a NET-basis plan — expectations derived from the
    engine's own breakdown rather than hand-pinned (the NET gross-up maths
    is pinned in `pricing/tests/test_engine_price_basis.py`)."""
    from pricing.services import PricingEngine
    from properties.enums import PriceBasis

    plan.price_basis = PriceBasis.NET.value
    plan.save(update_fields=["price_basis"])
    _finance(
        property_,
        commission_calculation_type="percent",
        commission_amount=Decimal("20"),
        tax_percentage=Decimal("13"),
        tax_is_exempt=False,
    )
    _make_noncomm_extra(property_, gbp)

    quote = PricingEngine.quote(
        property=property_,
        date_from=booking.date_from,
        date_to=booking.date_to,
        party=2,
        currency=gbp,
    )
    total = Decimal(str(quote.breakdown["total"]))
    commission = Decimal(str(quote.breakdown["commission"]))
    tax = Decimal(str(quote.breakdown["tax"]))
    net = Decimal(str(quote.breakdown["net_to_owner"]))
    assert quote.breakdown["extras_non_commissionable_total"] == "100.00"

    _set_snapshot(booking, quote.breakdown)
    deposit_gross = (total * Decimal("0.30")).quantize(Decimal("0.01"))
    _payment(booking, purpose="deposit", amount=str(deposit_gross))
    _payment(booking, purpose="balance", amount=str(total - deposit_gross))

    splits = payment_component_splits(booking)

    assert splits is not None
    deposit, balance = splits
    expected_dep_comm = (commission * deposit_gross / total).quantize(Decimal("0.01"))
    expected_dep_tax = (tax * deposit_gross / total).quantize(Decimal("0.01"))
    assert deposit["commission"] == expected_dep_comm
    assert deposit["tax"] == expected_dep_tax
    assert balance["commission"] == commission - expected_dep_comm
    assert balance["tax"] == tax - expected_dep_tax
    assert sum(s["net_to_owner"] for s in splits) == net
    for s in splits:
        assert s["net_to_owner"] == s["gross"] - s["commission"] - s["tax"]


# ----------------------------------------------------------------------
# Manual charge items overlay (GAP-076 `charges_owner_adjustments`)
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_splits__charge_items_overlay_post_charge_figures(
    booking: Booking, property_: Property
) -> None:
    """Splits allocate the post-charge owner money: a commissionable charge
    is skimmed at the property percent, a non-commissionable one passes
    through — exactly `owner_money_for_booking`'s figures."""
    from reservations.models import BookingChargeItem

    _finance(
        property_,
        commission_calculation_type="percent",
        commission_amount=Decimal("20"),
    )
    _set_snapshot(
        booking,
        {"total": "1000.00", "commission": "200.00", "tax": "100.00", "net_to_owner": "700.00"},
    )
    BookingChargeItem.objects.create(
        booking=booking,
        label="Late checkout",
        amount=Decimal("100.00"),
        currency=booking.currency,
        commissionable=True,
    )
    BookingChargeItem.objects.create(
        booking=booking,
        label="Chef",
        amount=Decimal("50.00"),
        currency=booking.currency,
        commissionable=False,
    )
    # Post-charge owner money: gross 1,150 / commission 220 / tax 100 / net 830.
    _payment(booking, purpose="deposit", amount="345.00")  # 30% of 1,150
    _payment(booking, purpose="balance", amount="805.00")

    splits = payment_component_splits(booking)

    assert splits is not None
    deposit, balance = splits
    assert deposit["commission"] == Decimal("66.00")  # 220 x 345/1150
    assert deposit["tax"] == Decimal("30.00")
    assert deposit["net_to_owner"] == Decimal("249.00")
    assert balance["commission"] == Decimal("154.00")
    assert balance["tax"] == Decimal("70.00")
    assert balance["net_to_owner"] == Decimal("581.00")
    assert sum(s["net_to_owner"] for s in splits) == Decimal("830.00")


# ----------------------------------------------------------------------
# Drift: Σ component gross ≠ booking gross is a routine state
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_splits__partial_mark_paid_drift_keeps_row_identities(
    booking: Booking, property_: Property
) -> None:
    """Operator partial `mark_paid` overwrote the deposit 3,000 → 2,000 with
    no resync (G = 9,000 < 10,000). Allocation runs over G: Σ commission and
    Σ tax still equal the whole-booking figures and every row satisfies
    net = gross - commission - tax; Σ net understates the whole-booking net
    by exactly the uncollected gross (the FE renders the caveat)."""
    _finance(property_)
    _set_snapshot(booking, GAP079_SNAPSHOT)
    _payment(booking, purpose="deposit", amount="2000.00", status="succeeded")
    _payment(booking, purpose="balance", amount="7000.00")

    splits = payment_component_splits(booking)

    assert splits is not None
    deposit, balance = splits
    assert deposit["status"] == "succeeded"
    assert deposit["commission"] == Decimal("386.67")  # 1740 x 2/9
    assert deposit["tax"] == Decimal("288.89")
    assert balance["commission"] == Decimal("1353.33")
    assert balance["tax"] == Decimal("1011.11")
    assert sum(s["commission"] for s in splits) == Decimal("1740.00")
    assert sum(s["tax"] for s in splits) == Decimal("1300.00")
    for s in splits:
        assert s["net_to_owner"] == s["gross"] - s["commission"] - s["tax"]
    # Σ net ≠ whole net — off by the 1,000 gross not (yet) scheduled.
    assert sum(s["net_to_owner"] for s in splits) == Decimal("5960.00")


@pytest.mark.django_db
def test_splits__manual_extra_row_drift(booking: Booking, property_: Property) -> None:
    """A waived BALANCE row plus its manual replacement both count as
    "scheduled" (track semantics), so G = 10,500 > 10,000: same identities —
    Σ commission/tax exact, per-row consistency, Σ net overstates by the
    extra scheduled gross. (Two *active* rows per purpose are barred by
    `unique_active_balance_per_booking`; waived + pending is the
    constraint-legal shape this drift really takes.)"""
    _finance(property_)
    _set_snapshot(booking, GAP079_SNAPSHOT)
    _payment(booking, purpose="deposit", amount="3000.00")
    _payment(booking, purpose="balance", amount="7000.00", status="waived")
    _payment(booking, purpose="balance", amount="500.00")  # manual track row

    splits = payment_component_splits(booking)

    assert splits is not None
    deposit, balance = splits
    assert balance["gross"] == Decimal("7500.00")
    assert deposit["commission"] == Decimal("497.14")  # 1740 x 3000/10500
    assert deposit["tax"] == Decimal("371.43")
    assert balance["commission"] == Decimal("1242.86")
    assert balance["tax"] == Decimal("928.57")
    assert sum(s["commission"] for s in splits) == Decimal("1740.00")
    assert sum(s["tax"] for s in splits) == Decimal("1300.00")
    assert sum(s["net_to_owner"] for s in splits) == Decimal("7460.00")  # 6960 + 500


# ----------------------------------------------------------------------
# Track-semantics mirroring + edge cases
# ----------------------------------------------------------------------
@pytest.mark.django_db
def test_splits__cancelled_rows_excluded_and_status_is_latest_row(
    booking: Booking, property_: Property
) -> None:
    """Gross uses the track "scheduled" filter (status ∉ {cancelled, expired,
    failed}); component status mirrors the track's latest-row semantics."""
    _finance(property_)
    _set_snapshot(booking, GAP079_SNAPSHOT)
    _payment(booking, purpose="deposit", amount="3000.00", status="cancelled")
    _payment(booking, purpose="deposit", amount="3000.00")  # replacement row
    _payment(booking, purpose="balance", amount="7000.00", status="waived")

    splits = payment_component_splits(booking)

    assert splits is not None
    deposit, balance = splits
    assert deposit["gross"] == Decimal("3000.00")  # not 6,000
    assert deposit["status"] == "pending"  # latest row wins
    assert balance["gross"] == Decimal("7000.00")  # waived still scheduled
    assert balance["status"] == "waived"


@pytest.mark.django_db
def test_splits__due_at_is_earliest_scheduled_including_succeeded(
    booking: Booking, property_: Property
) -> None:
    """due_at mirrors the track next-due: earliest among scheduled rows —
    including SUCCEEDED (a settled deposit still reports its due date) and
    WAIVED ones (`track.py` semantics)."""
    _finance(property_)
    _set_snapshot(booking, GAP079_SNAPSHOT)
    early = timezone.now() - timedelta(days=10)
    late = timezone.now() + timedelta(days=5)
    _payment(booking, purpose="deposit", amount="3000.00", status="succeeded", due_at=early)
    _payment(booking, purpose="balance", amount="7000.00", status="waived", due_at=early)
    _payment(booking, purpose="balance", amount="0.00", due_at=late)

    splits = payment_component_splits(booking)

    assert splits is not None
    deposit, balance = splits
    assert deposit["due_at"] == early  # settled row still carries next-due
    assert balance["due_at"] == early  # earliest across waived + pending


@pytest.mark.django_db
def test_splits__sparse_snapshot_returns_none(booking: Booking) -> None:
    """Imported bookings carry `pricing_snapshot = {}` — no owner money, no
    split (mirrors `owner_money_for_booking`)."""
    _payment(booking, purpose="deposit", amount="420.00")
    assert payment_component_splits(booking) is None


@pytest.mark.django_db
def test_splits__no_payment_rows_returns_empty_list(booking: Booking) -> None:
    """A financeless property schedules nothing — the split is an empty
    list (distinct from None: the money exists, the schedule doesn't)."""
    _set_snapshot(booking, GAP079_SNAPSHOT)
    assert payment_component_splits(booking) == []


@pytest.mark.django_db
def test_splits__zero_gross_schedule_allocates_zero(booking: Booking, property_: Property) -> None:
    """All-zero rows (a resync clamped everything to 0) — no division error,
    zero allocations."""
    _finance(property_)
    _set_snapshot(booking, GAP079_SNAPSHOT)
    _payment(booking, purpose="deposit", amount="0.00")
    _payment(booking, purpose="balance", amount="0.00")

    splits = payment_component_splits(booking)

    assert splits is not None
    for s in splits:
        assert s["gross"] == Decimal("0.00")
        assert s["commission"] == Decimal("0.00")
        assert s["tax"] == Decimal("0.00")
        assert s["net_to_owner"] == Decimal("0.00")
