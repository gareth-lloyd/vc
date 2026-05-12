"""Tests for the `Guest` model — anonymize() and merge()."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from pricing.models import Currency
from properties.models import Property
from reservations.enums import GuestStatus, PaymentMethod
from reservations.models import (
    Booking,
    Guest,
    Quotation,
    QuotationLine,
    TermsVersion,
)


def _make_booking(
    *,
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> Booking:
    quotation = Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    line = QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        children=0,
        total=Decimal("1400.00"),
    )
    return Booking.objects.create(
        quotation_line=line,
        guest=guest,
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )


@pytest.mark.django_db
def test_anonymize_redacts_pii_and_preserves_fks(
    guest: Guest,
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    booking = _make_booking(guest=guest, property_=property_, gbp=gbp, terms=terms)

    guest.anonymize()

    guest.refresh_from_db()
    booking.refresh_from_db()
    assert guest.status == GuestStatus.ANONYMIZED.value
    assert guest.first_name == "[REDACTED]"
    assert guest.last_name == "[REDACTED]"
    assert guest.email == f"redacted-{guest.pk}@anonymized.local"
    assert guest.phone == ""
    assert guest.marketing_consent is False
    assert guest.anonymized_at is not None
    # FK survives — booking still points at the anonymized guest.
    assert booking.guest_id == guest.pk


@pytest.mark.django_db
def test_merge_rewrites_fks_and_hard_deletes_source(
    property_: Property,
    gbp: Currency,
    terms: TermsVersion,
) -> None:
    keep = Guest.objects.create(first_name="Keep", last_name="Me", email="keep@x.com")
    duplicate = Guest.objects.create(first_name="Dup", last_name="Me", email="dup@x.com")
    booking = _make_booking(guest=duplicate, property_=property_, gbp=gbp, terms=terms)

    duplicate.merge(keep)

    assert not Guest.objects.filter(pk=duplicate.pk).exists()
    booking.refresh_from_db()
    assert booking.guest_id == keep.pk


@pytest.mark.django_db
def test_merge_into_self_raises(guest: Guest) -> None:
    with pytest.raises(ValueError):
        guest.merge(guest)
