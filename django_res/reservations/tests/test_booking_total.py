"""Tests for `booking_total` — THE single guest grand-total authority (SMELL-020).

Every surface that answers "what does this booking cost the guest" (payment
scheduler, security-deposit sizing, charge breakdown, booking serializer,
charge-item negativity guard) must delegate here; these tests pin the one
formula: `pricing_snapshot["total"]` (str-coerced) else `balance_due`, plus
Σ charge items, quantized to 2dp.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from accounts.models import Person
from pricing.models import Currency
from properties.models import Property
from reservations.factories import BookingChargeItemFactory, make_occupying_booking
from reservations.models import Booking, TermsVersion
from reservations.services.charges import booking_total, charges_total_for, with_charges_total


@pytest.fixture
def booking(
    db: None,
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
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
def test_snapshot_total_plus_charges(booking: Booking, gbp: Currency) -> None:
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Late checkout", amount=Decimal("150.00")
    )
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Loyalty credit", amount=Decimal("-500.00")
    )

    assert booking_total(booking) == Decimal("1050.00")


@pytest.mark.django_db
def test_snapshot_wins_over_balance_due(booking: Booking) -> None:
    # The snapshot is the locked-in confirmation-time breakdown; a divergent
    # balance_due (manual edit) must not leak into the guest total.
    booking.balance_due = Decimal("999.99")
    booking.save(update_fields=["balance_due"])

    assert booking_total(booking) == Decimal("1400.00")


@pytest.mark.django_db
def test_empty_snapshot_falls_back_to_balance_due(booking: Booking, gbp: Currency) -> None:
    # Migrated bookings carry `pricing_snapshot={}` — the loader stamps only
    # `balance_due`, which then IS the base.
    booking.pricing_snapshot = {}
    booking.balance_due = Decimal("1200.00")
    booking.save(update_fields=["pricing_snapshot", "balance_due"])
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Extra cot", amount=Decimal("100.00")
    )

    assert booking_total(booking) == Decimal("1300.00")


@pytest.mark.django_db
def test_none_snapshot_falls_back_to_balance_due(booking: Booking) -> None:
    booking.pricing_snapshot = None
    booking.balance_due = Decimal("900.00")

    assert booking_total(booking) == Decimal("900.00")


@pytest.mark.django_db
def test_float_snapshot_total_is_str_coerced(booking: Booking) -> None:
    # A real JSON decode yields a float — `str()`-coercion, not
    # `Decimal(float)`, so there is no binary-float drift.
    booking.pricing_snapshot = {"total": 1450.5}

    assert booking_total(booking) == Decimal("1450.50")


@pytest.mark.django_db
def test_result_is_quantized_to_two_places(booking: Booking) -> None:
    booking.pricing_snapshot = {"total": "1400"}

    total = booking_total(booking)

    assert total == Decimal("1400.00")
    assert total.as_tuple().exponent == -2


@pytest.mark.django_db
def test_stale_annotation_is_ignored_by_default(booking: Booking, gbp: Currency) -> None:
    # Safe-by-default: without an explicit `charges_total`, the authority
    # live-aggregates — a `with_charges_total` annotation computed before a
    # later charge write must NOT be believed when sizing real money.
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Late checkout", amount=Decimal("150.00")
    )
    annotated = with_charges_total(Booking.objects.all()).get(pk=booking.pk)
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Heli transfer", amount=Decimal("900.00")
    )

    assert getattr(annotated, "charges_total", None) == Decimal("150.00")  # stale
    assert booking_total(annotated) == Decimal("2450.00")  # live


@pytest.mark.django_db
def test_annotation_read_is_query_free_via_explicit_passthrough(
    booking: Booking, gbp: Currency
) -> None:
    # Annotated list/detail paths opt out of the aggregate by handing over
    # the annotation sum explicitly (via `charges_total_for`) — zero queries.
    from core.tests import assert_max_queries

    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Late checkout", amount=Decimal("150.00")
    )
    annotated = with_charges_total(Booking.objects.all()).get(pk=booking.pk)

    with assert_max_queries(0):
        total = booking_total(annotated, charges_total=charges_total_for(annotated))
    assert total == Decimal("1550.00")


@pytest.mark.django_db
def test_charges_total_zero_passthrough_is_query_free(booking: Booking) -> None:
    # `booking_charge_breakdown` hands over its single-pass sum — legitimately
    # `Decimal("0")` for a charge-less booking. The keyword check must be
    # `is None`, not truthiness, or the zero-charge prefetched path re-queries.
    from core.tests import assert_max_queries

    with assert_max_queries(0):
        assert booking_total(booking, charges_total=Decimal("0")) == Decimal("1400.00")


@pytest.mark.django_db
def test_charges_total_passthrough_overrides_db(booking: Booking, gbp: Currency) -> None:
    BookingChargeItemFactory(
        booking=booking, currency=gbp, label="Late checkout", amount=Decimal("150.00")
    )

    assert booking_total(booking, charges_total=Decimal("25.00")) == Decimal("1425.00")
