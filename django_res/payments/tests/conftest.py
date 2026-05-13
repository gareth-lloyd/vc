"""Test fixtures for the payments app.

Builds a minimal Booking graph so payment-side tests don't have to know
every upstream factory.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from pricing.models import Currency

if TYPE_CHECKING:
    from accounts.models import User
    from properties.models import Property
    from reservations.models import Booking, Guest, QuotationLine, TermsVersion


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.fixture
def property_(db: None) -> Property:
    from properties.models import (
        Country,
        Property,
        PropertyCategory,
        PropertyGroup,
        Region,
    )

    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    region = Region.objects.create(country=country, name="South West", slug="south-west")
    category = PropertyCategory.objects.create(name="Villa", slug="villa")
    group = PropertyGroup.objects.create(name="Test group")
    return Property.objects.create(
        name="Test Villa",
        display_name="Test Villa",
        slug="test-villa",
        category=category,
        group=group,
        region=region,
    )


@pytest.fixture
def guest(db: None) -> Guest:
    from reservations.models import Guest

    return Guest.objects.create(
        first_name="Ada",
        last_name="Lovelace",
        email="ada-payments@example.com",
    )


@pytest.fixture
def terms(db: None) -> TermsVersion:
    from reservations.models import TermsVersion

    return TermsVersion.objects.create(
        version="2026-01",
        body_markdown="**T&Cs**",
        published_at=timezone.now(),
        is_current=True,
    )


@pytest.fixture
def quotation_line(
    db: None,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> QuotationLine:
    from reservations.models import Quotation, QuotationLine

    quotation = Quotation.objects.create(
        guest=guest,
        currency=gbp,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    date_from = date.today() + timedelta(days=60)
    date_to = date_from + timedelta(days=7)
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        date_from=date_from,
        date_to=date_to,
        adults=2,
        total=Decimal("1400.00"),
    )


@pytest.fixture
def booking(
    db: None,
    quotation_line: QuotationLine,
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> Booking:
    from reservations.enums import PaymentMethod
    from reservations.models import Booking

    return Booking.objects.create(
        quotation_line=quotation_line,
        guest=guest,
        property=property_,
        date_from=quotation_line.date_from,
        date_to=quotation_line.date_to,
        adults=quotation_line.adults,
        children=0,
        currency=gbp,
        terms_version=terms,
        terms_accepted_at=timezone.now(),
        payment_method=PaymentMethod.CARD.value,
        rental_price=Decimal("1400.00"),
        balance_due=Decimal("1400.00"),
    )


@pytest.fixture
def user(db: None) -> User:
    from accounts.models import User

    return User.objects.create_user(
        email="requester@example.com",
        password="testpass-1",
    )


@pytest.fixture
def approver(db: None) -> User:
    from accounts.models import User

    return User.objects.create_user(
        email="approver@example.com",
        password="testpass-2",
    )
