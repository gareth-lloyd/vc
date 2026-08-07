"""GAP-087 verify-only: a per-booking deposit override reshapes every
derive-on-read money surface.

The override sizes the DEPOSIT/BALANCE Payment rows (Unit 2); both
`payment_component_splits` (FinanceTab authority) and the GAP-085 Zoho
`financials` block derive from those live rows, so an overridden deposit must
flow through to both with no extra wiring. These tests guard against a future
regression that stops deriving from the live schedule.

Test scaffolding may import `payments` (the layers contract ignores
`*.tests.**`); the services under test must not.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from payments.services import PaymentScheduler
from properties.models import PropertyFinance
from reservations.models import Booking
from reservations.services.owner_finance import payment_component_splits
from reservations.services.zoho_payload import build_booking_payload

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import TermsVersion


@pytest.fixture
def overridden_booking(
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    """AWAITING_DEPOSIT booking (total 1,400) with a 500 deposit override and a
    schedule sized against it (deposit 500 / balance 900)."""
    from reservations.factories import make_occupying_booking

    booking = make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    PropertyFinance.objects.get_or_create(property=property_)
    Booking.objects.filter(pk=booking.pk).update(
        deposit_override_amount=Decimal("500.00"),
        balance_due=Decimal("1400.00"),
        pricing_snapshot={
            "total": "1400.00",
            "commission": "200.00",
            "tax": "100.00",
            "net_to_owner": "1100.00",
            "price_basis": "gross",
        },
    )
    fresh = Booking.objects.get(pk=booking.pk)
    PaymentScheduler.create_for_booking(fresh)
    return fresh


@pytest.mark.django_db
def test_override_flows_through_to_payment_component_splits(
    overridden_booking: Booking,
) -> None:
    """The FinanceTab split reflects the overridden deposit/balance gross."""
    splits = payment_component_splits(overridden_booking)

    assert splits is not None
    by_purpose = {s["purpose"]: s for s in splits}
    assert by_purpose["deposit"]["gross"] == Decimal("500.00")
    assert by_purpose["balance"]["gross"] == Decimal("900.00")


@pytest.mark.django_db
def test_override_flows_through_to_zoho_financials(overridden_booking: Booking) -> None:
    """The GAP-085 Zoho `financials` block shows the overridden figures."""
    financials = build_booking_payload(overridden_booking)["financials"]

    assert financials["total_gross"] == "1400.00"
    assert financials["gross_deposit"] == "500.00"
    assert financials["gross_balance"] == "900.00"


@pytest.mark.django_db
def test_carry_over_walkthrough_end_to_end(
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> None:
    """The acceptance proof for the 2026-07-29 cancellation carry-over workaround.

    Cancel booking A → create booking B → override B's deposit (net of the
    carried-over credit) → mark that deposit paid offline → the deposit settles
    at the overridden figure, the balance is the remainder, both money surfaces
    reflect it, and a later charge edit preserves the override.
    """
    from datetime import UTC, datetime

    from payments.enums import PaymentPurpose, PaymentStatus
    from payments.models import Payment
    from reservations.enums import PaymentMethod as BookingPaymentMethod
    from reservations.factories import make_occupying_booking
    from reservations.models import BookingChargeItem

    PropertyFinance.objects.get_or_create(property=property_)

    # Booking A — cancelled (the carry-over source; its credit is applied
    # manually as booking B's override, no automation).
    booking_a = make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
    )
    booking_a.cancel("Carried over to a new booking", actor=None)
    assert booking_a.status == "cancelled"

    # Booking B — the replacement, deposit netted down to 500 via the override.
    booking_b = make_occupying_booking(
        property=property_,
        person=customer,
        currency=gbp,
        terms=terms,
        date_from=date(2026, 8, 10),
        date_to=date(2026, 8, 17),
    )
    Booking.objects.filter(pk=booking_b.pk).update(
        balance_due=Decimal("1400.00"),
        pricing_snapshot={
            "total": "1400.00",
            "commission": "200.00",
            "tax": "100.00",
            "net_to_owner": "1100.00",
            "price_basis": "gross",
        },
    )
    booking_b = Booking.objects.get(pk=booking_b.pk)
    booking_b.status = "awaiting_deposit"
    booking_b.save(update_fields=["status"])
    PaymentScheduler.create_for_booking(booking_b)

    booking_b.set_deposit_override(Decimal("500.00"), reason="Carry-over credit from A")

    deposit = Payment.objects.get(booking=booking_b, purpose=PaymentPurpose.DEPOSIT.value)
    balance = Payment.objects.get(booking=booking_b, purpose=PaymentPurpose.BALANCE.value)
    assert deposit.amount == Decimal("500.00")
    assert balance.amount == Decimal("900.00")

    # Mark the (overridden) deposit paid offline — no provider transaction.
    deposit.mark_paid(
        amount=Decimal("500.00"),
        paid_at=datetime(2026, 8, 1, tzinfo=UTC),
        method=BookingPaymentMethod.BANK_TRANSFER.value,
        reference="carry-over",
    )
    deposit.refresh_from_db()
    assert deposit.status == PaymentStatus.SUCCEEDED.value
    assert deposit.amount == Decimal("500.00")

    # Money surfaces reflect the overridden deposit.
    splits = {s["purpose"]: s for s in payment_component_splits(booking_b) or []}
    assert splits["deposit"]["gross"] == Decimal("500.00")
    financials = build_booking_payload(booking_b)["financials"]
    assert financials["gross_deposit"] == "500.00"

    # A later charge edit resyncs the balance but never revives the settled
    # deposit off policy — the override figure stands.
    BookingChargeItem.objects.create(
        booking=booking_b, label="Late checkout", amount=Decimal("200.00"), currency=gbp
    )
    deposit.refresh_from_db()
    balance.refresh_from_db()
    assert deposit.amount == Decimal("500.00")
    assert balance.amount == Decimal("1100.00")  # (1400 + 200) minus 500 settled
