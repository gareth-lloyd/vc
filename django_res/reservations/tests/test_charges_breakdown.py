"""Tests for `booking_charge_breakdown` — the guest-facing charge itemisation.

The breakdown decomposes the total a guest is billed into the snapshot base
plus the signed `BookingChargeItem` lines (legacy `VillaBookingDetail`
itemisation), partitioned by sign into `charges` (positive) and `discounts`
(negative). The grand `total` must come from `booking_total` — the single
money authority (SMELL-020) — so the email total matches the scheduled total.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from accounts.models import Person
from pricing.models import Currency
from properties.models import Property
from reservations.factories import BookingChargeItemFactory, make_occupying_booking
from reservations.models import Booking, TermsVersion
from reservations.services.charges import _money, booking_charge_breakdown, booking_total


@pytest.fixture
def booking(
    db: None,
    customer: Person,
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
        person=customer,
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
    # 1400 + 150 + 900 - 500 = 1950 — equals `booking_total`.
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
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    # No snapshot total set → base falls back to `balance_due` (mirrors the
    # scheduler), NOT a non-existent `booking.total`.
    booking = make_occupying_booking(
        property=property_,
        person=customer,
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
def test_builder_is_query_free_when_booking_is_prefetched(
    db: None,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    # The comms/payments callers `select_related("…currency")` +
    # `prefetch_related("…charge_items")` so the per-row builder adds ZERO
    # queries across a reminder batch (H2 — no per-booking N+1). Pin that the
    # builder reads only the prefetch cache + select_related + local columns.
    from core.tests import assert_max_queries

    for offset in (0, 14):
        other = make_occupying_booking(
            property=property_,
            person=customer,
            currency=gbp,
            terms=terms,
            date_from=date(2026, 6, 10) + timedelta(days=offset),
            date_to=date(2026, 6, 17) + timedelta(days=offset),
        )
        BookingChargeItemFactory(
            booking=other, currency=gbp, label="Late checkout", amount=Decimal("150.00")
        )
        BookingChargeItemFactory(
            booking=other, currency=gbp, label="Loyalty credit", amount=Decimal("-50.00")
        )

    bookings = list(Booking.objects.select_related("currency").prefetch_related("charge_items"))
    assert len(bookings) == 2

    with assert_max_queries(0):
        for prefetched in bookings:
            booking_charge_breakdown(prefetched)


@pytest.mark.django_db
def test_total_matches_booking_total_live_aggregate(booking: Booking, gbp: Currency) -> None:
    # The email total == scheduled total invariant now holds by construction:
    # both the breakdown and PaymentScheduler delegate to `booking_total`
    # (SMELL-020). What is left to pin is the passthrough seam — the
    # breakdown's single-pass `charges_total=` sum must equal the authority's
    # own live aggregate.
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Late checkout", amount=Decimal("150.00")
    )
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Loyalty credit", amount=Decimal("-500.00")
    )

    result = booking_charge_breakdown(booking)

    assert result["total"] == _money(booking_total(booking))


@pytest.mark.django_db
def test_float_snapshot_total_is_str_coerced(booking: Booking, gbp: Currency) -> None:
    # A real JSON decode yields a float, not a str — the base extraction must
    # `str()`-coerce it, with no binary-float drift.
    booking.pricing_snapshot = {"total": 1450.5}
    booking.save(update_fields=["pricing_snapshot"])
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Extra cot", amount=Decimal("100.00")
    )

    result = booking_charge_breakdown(booking)

    assert result["base_amount"] == "1,450.50"
    assert result["total"] == _money(booking_total(booking))


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
