"""BookingConciergeItem is NON-SCHEDULING money (SMELL-020).

Concierge lines never enter `booking_total()` (the single guest-total
authority), never fire `booking_total_changed`, and never resize the payment
schedule or the security deposit. Collection is deferred to the future
`Payment(purpose=CONCIERGE)` — `ConciergeService.request_payment` is the
(stubbed) seam. The old `Booking.adjustment` denorm these lines used to
maintain was written-but-never-read and has been removed.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from reservations.enums import ConciergeTier, ConciergeUnit, PaymentMethod
from reservations.models import (
    Booking,
    BookingConciergeItem,
    Quotation,
    QuotationLine,
)
from reservations.services.charges import booking_total
from reservations.services.concierge import ConciergeService
from reservations.signals import booking_total_changed

if TYPE_CHECKING:
    from accounts.models import Person
    from pricing.models import Currency
    from properties.models import Property
    from reservations.models import TermsVersion


@pytest.fixture
def booking(
    customer: Person,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    person = customer
    quotation = Quotation.objects.create(
        enquiry=person.enquiries_as_customer.create(),
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        person=person,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )


def _chef(booking: Booking, gbp: Currency) -> BookingConciergeItem:
    return BookingConciergeItem.objects.create(
        booking=booking,
        tier=ConciergeTier.SIGNATURE.value,
        name="Private chef",
        quantity=2,
        unit=ConciergeUnit.EVENT.value,
        unit_price=Decimal("300.00"),
        currency=gbp,
    )


@pytest.mark.django_db
def test_concierge_item_never_enters_booking_total(booking: Booking, gbp: Currency) -> None:
    assert booking_total(booking) == Decimal("1400.00")

    item = _chef(booking, gbp)
    assert booking_total(booking) == Decimal("1400.00")

    item.delete()
    assert booking_total(booking) == Decimal("1400.00")


@pytest.mark.django_db
def test_concierge_item_fires_no_booking_total_changed(booking: Booking, gbp: Currency) -> None:
    fired: list[Booking] = []

    def _capture(sender: type, booking: Booking, **_: object) -> None:
        fired.append(booking)

    booking_total_changed.connect(_capture, dispatch_uid="test.concierge_no_total_changed")
    try:
        item = _chef(booking, gbp)
        item.delete()
    finally:
        booking_total_changed.disconnect(dispatch_uid="test.concierge_no_total_changed")

    assert fired == []


@pytest.mark.django_db
def test_concierge_item_leaves_payment_schedule_untouched(
    booking: Booking, gbp: Currency, property_: Property
) -> None:
    from payments.models import Payment, SecurityDeposit
    from payments.services.payment_scheduler import PaymentScheduler
    from properties.models.finance import PropertyFinance

    PropertyFinance.objects.get_or_create(property=property_)
    booking = Booking.objects.get(pk=booking.pk)  # refresh cached `.finance`
    rows = PaymentScheduler.create_for_booking(booking)
    assert rows  # non-vacuous: the default policy floor yields deposit+balance
    before = {row.pk: row.amount for row in rows}

    _chef(booking, gbp)

    # No resize, no new collection row, no security-deposit reaction.
    assert {p.pk: p.amount for p in Payment.objects.filter(booking=booking)} == before
    assert not SecurityDeposit.objects.filter(booking=booking).exists()


@pytest.mark.django_db
def test_request_payment_is_a_pending_stub(booking: Booking, gbp: Currency) -> None:
    # The Payment(purpose=CONCIERGE) collection path is the deferred design —
    # the stable seam exists, the implementation deliberately does not yet.
    item = _chef(booking, gbp)
    with pytest.raises(NotImplementedError):
        ConciergeService.request_payment(item)
