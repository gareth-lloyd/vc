"""Tests for `booking_charge_breakdown` — the guest-facing charge itemisation.

The breakdown decomposes the total a guest is billed into the snapshot base
plus the signed `BookingChargeItem` lines (legacy `VillaBookingDetail`
itemisation), partitioned by sign into `charges` (positive) and `discounts`
(negative). The grand `total` must equal `PaymentScheduler._booking_total`
byte-for-byte so the email total matches the scheduled total.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from payments.services.payment_scheduler import PaymentScheduler
from pricing.models import Currency
from properties.models import Property
from reservations.factories import BookingChargeItemFactory, make_occupying_booking
from reservations.models import Booking, Guest, TermsVersion
from reservations.services.charges import _money, booking_charge_breakdown


@pytest.fixture
def booking(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    """An occupying booking with an explicit snapshot total.

    `make_occupying_booking` leaves `pricing_snapshot={}`/`balance_due=0`, so a
    test that wants a snapshot base must set it itself (mirrors the real
    confirmation-time snapshot).
    """
    booking = make_occupying_booking(
        property=property_,
        guest=guest,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    booking.pricing_snapshot = {"total": "1400.00"}
    booking.save(update_fields=["pricing_snapshot"])
    return booking


@pytest.mark.django_db
def test_partitions_charges_and_discounts_in_pk_order(booking: Booking, gbp: Currency) -> None:
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Late checkout", amount=Decimal("150.00")
    )
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Heli transfer", amount=Decimal("900.00")
    )
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Loyalty credit", amount=Decimal("-500.00")
    )

    result = booking_charge_breakdown(booking)

    assert result["currency"] == "GBP"
    assert result["base_amount"] == "1,400.00"
    assert result["charges"] == [
        {"label": "Late checkout", "amount": "150.00"},
        {"label": "Heli transfer", "amount": "900.00"},
    ]
    assert result["discounts"] == [
        {"label": "Loyalty credit", "amount": "-500.00"},
    ]
    # 1400 + 150 + 900 - 500 = 1950 — equals PaymentScheduler._booking_total.
    assert result["total"] == "1,950.00"


@pytest.mark.django_db
def test_thousands_grouping_on_large_total(booking: Booking, gbp: Currency) -> None:
    booking.pricing_snapshot = {"total": "12000.00"}
    booking.save(update_fields=["pricing_snapshot"])
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Yacht day", amount=Decimal("3500.50")
    )

    result = booking_charge_breakdown(booking)

    assert result["base_amount"] == "12,000.00"
    assert result["charges"] == [{"label": "Yacht day", "amount": "3,500.50"}]
    assert result["total"] == "15,500.50"


@pytest.mark.django_db
def test_no_charge_items_renders_base_as_total(booking: Booking) -> None:
    result = booking_charge_breakdown(booking)

    assert result["charges"] == []
    assert result["discounts"] == []
    assert result["base_amount"] == "1,400.00"
    assert result["total"] == "1,400.00"


@pytest.mark.django_db
def test_falls_back_to_balance_due_without_snapshot(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    # No snapshot total set → base falls back to `balance_due` (mirrors the
    # scheduler), NOT a non-existent `booking.total`.
    booking = make_occupying_booking(
        property=property_,
        guest=guest,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    booking.balance_due = Decimal("1200.00")
    booking.save(update_fields=["balance_due"])
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Extra cot", amount=Decimal("100.00")
    )

    result = booking_charge_breakdown(booking)

    assert result["base_amount"] == "1,200.00"
    assert result["total"] == "1,300.00"


@pytest.mark.django_db
def test_total_is_byte_equal_to_payment_scheduler(booking: Booking, gbp: Currency) -> None:
    # The load-bearing invariant: the email's grand total MUST equal what the
    # guest is actually scheduled to pay. Pin it against the real scheduler
    # method rather than a hand-typed literal, so a future change to
    # `_booking_total` (e.g. switching its flat quantize to currency-aware
    # `quantise_money`) fails here instead of silently drifting the email.
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Late checkout", amount=Decimal("150.00")
    )
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Loyalty credit", amount=Decimal("-500.00")
    )

    result = booking_charge_breakdown(booking)

    assert result["total"] == _money(PaymentScheduler._booking_total(booking))


@pytest.mark.django_db
def test_float_snapshot_total_is_str_coerced(booking: Booking, gbp: Currency) -> None:
    # A real JSON decode yields a float, not a str — the builder must `str()`-
    # coerce it exactly as the scheduler does, with no binary-float drift.
    booking.pricing_snapshot = {"total": 1450.5}
    booking.save(update_fields=["pricing_snapshot"])
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Extra cot", amount=Decimal("100.00")
    )

    result = booking_charge_breakdown(booking)

    assert result["base_amount"] == "1,450.50"
    assert result["total"] == _money(PaymentScheduler._booking_total(booking))


@pytest.mark.django_db
def test_none_snapshot_falls_back_to_balance_due(booking: Booking, gbp: Currency) -> None:
    # Belt-and-suspenders for the `... or {}` guard: a None snapshot (vs the
    # default `{}`) must still fall back to `balance_due`. Set it in memory —
    # the column is non-null, so this exercises the guard without a write.
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Extra cot", amount=Decimal("100.00")
    )
    booking.pricing_snapshot = None
    booking.balance_due = Decimal("900.00")

    result = booking_charge_breakdown(booking)

    assert result["base_amount"] == "900.00"
    assert result["total"] == "1,000.00"
