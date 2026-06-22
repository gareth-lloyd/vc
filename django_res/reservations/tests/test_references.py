"""Customer-facing reference parity with legacy `ResSystem` (GAP-006).

Legacy rendered a quotation as `QVC{QuotationNo}` and the resulting booking as
`VC{QuotationNo}` — same digits, prefix swapped, the booking number *carried
forward* from the quotation rather than drawn from an independent sequence.
These tests pin that contract on the rebuild.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from core.models.system_settings import SystemSettings
from pricing.models import Currency
from properties.models import Property
from reservations.enums import PaymentMethod
from reservations.models import (
    Booking,
    Quotation,
    QuotationLine,
    TermsVersion,
)

if TYPE_CHECKING:
    from accounts.models import Person


def _make_quotation(customer: Person, gbp: Currency, terms: TermsVersion) -> Quotation:
    return Quotation.objects.create(
        enquiry=customer.enquiries_as_customer.create(),
        person=customer,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )


def _make_booking(
    line: QuotationLine, customer: Person, gbp: Currency, terms: TermsVersion
) -> Booking:
    return Booking.objects.create(
        quotation_line=line,
        person=customer,
        property=line.property,
        date_from=line.date_from,
        date_to=line.date_to,
        adults=line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
    )


@pytest.mark.django_db
def test_quotation_number_allocated_and_reference_derived(
    customer: Person, gbp: Currency, terms: TermsVersion
) -> None:
    quotation = _make_quotation(customer, gbp, terms)
    assert quotation.number is not None
    assert quotation.reference == f"QVC{quotation.number}"


@pytest.mark.django_db
def test_quotation_numbers_are_unique_and_monotonic(
    customer: Person, gbp: Currency, terms: TermsVersion
) -> None:
    first = _make_quotation(customer, gbp, terms)
    second = _make_quotation(customer, gbp, terms)
    assert first.number is not None and second.number is not None
    assert second.number > first.number
    assert first.reference != second.reference


@pytest.mark.django_db
def test_booking_carries_quotation_number_forward(
    quotation_line: QuotationLine, customer: Person, gbp: Currency, terms: TermsVersion
) -> None:
    booking = _make_booking(quotation_line, customer, gbp, terms)
    quotation = quotation_line.quotation
    assert quotation.number is not None
    # Same digits, prefix swapped — `QVC{n}` → `VC{n}`.
    assert booking.reference == f"VC{quotation.number}"
    assert quotation.reference == f"QVC{quotation.number}"


@pytest.mark.django_db
def test_prefixes_overridable_via_system_settings(
    property_: Property, customer: Person, gbp: Currency, terms: TermsVersion
) -> None:
    settings = SystemSettings.get_solo()
    settings.settings["quotation_no_prefix"] = "Q-CUSTOM-"
    settings.settings["booking_no_prefix"] = "B-CUSTOM-"
    settings.save()

    quotation = _make_quotation(customer, gbp, terms)
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
    booking = _make_booking(line, customer, gbp, terms)

    assert quotation.reference == f"Q-CUSTOM-{quotation.number}"
    assert booking.reference == f"B-CUSTOM-{quotation.number}"


@pytest.mark.django_db
def test_booking_off_numberless_quotation_uses_interim_sentinel(
    quotation_line: QuotationLine, customer: Person, gbp: Currency, terms: TermsVersion
) -> None:
    """A quotation with no `number` (synthesised/interim legacy row) must yield a
    non-numeric booking sentinel, never a bare `VC{int}`."""
    quotation = quotation_line.quotation
    Quotation.objects.filter(pk=quotation.pk).update(
        number=None, reference=f"QVC-TMP-{quotation.pk}"
    )
    quotation_line.quotation.refresh_from_db()

    booking = _make_booking(quotation_line, customer, gbp, terms)
    assert booking.reference.startswith("VC-TMP")


@pytest.mark.django_db
def test_derive_reference_appends_suffix_on_collision(
    quotation_line: QuotationLine, customer: Person, gbp: Currency, terms: TermsVersion
) -> None:
    """Defensive only — the real flow is one quote → one booking, so the
    carry-forward value is unique by construction. Constructed here by deriving
    twice off the same quotation_line."""
    first = _make_booking(quotation_line, customer, gbp, terms)
    quotation = quotation_line.quotation
    assert first.reference == f"VC{quotation.number}"

    second = Booking(
        quotation_line=quotation_line,
        person=customer,
        property=quotation_line.property,
        date_from=quotation_line.date_from,
        date_to=quotation_line.date_to,
        adults=quotation_line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
    )
    derived = second._derive_reference()
    assert derived.startswith(f"VC{quotation.number}-")
    assert derived != first.reference


@pytest.mark.django_db
def test_resaving_a_booking_keeps_its_reference_stable(
    quotation_line: QuotationLine, customer: Person, gbp: Currency, terms: TermsVersion
) -> None:
    """Re-deriving a saved booking's reference must not see *itself* as a
    collision and append a spurious suffix (the helper excludes its own pk)."""
    booking = _make_booking(quotation_line, customer, gbp, terms)
    original = booking.reference

    rederived = booking._derive_reference()
    assert rederived == original


@pytest.mark.django_db
def test_references_fit_field_width(
    quotation_line: QuotationLine, customer: Person, gbp: Currency, terms: TermsVersion
) -> None:
    booking = _make_booking(quotation_line, customer, gbp, terms)
    quotation = quotation_line.quotation
    assert len(quotation.reference) <= 32
    assert len(booking.reference) <= 32
