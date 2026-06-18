"""Reservations test fixtures.

Builds the minimum property + pricing graph so tests can spin up
Quotations and Bookings without coupling to every upstream factory.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone

from pricing.models import Currency, RateCard, RatePlan, RateRule
from reservations.models import Guest, Quotation, QuotationLine, TermsVersion
from reservations.services.person_sync import person_for_guest

if TYPE_CHECKING:
    from properties.models import Property


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.fixture
def property_(db: None) -> Property:
    """Build a minimal property graph for reservations tests."""
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
def plan(property_: Property, gbp: Currency) -> RatePlan:
    return RatePlan.objects.create(
        property=property_,
        name="Summer 2026",
        currency=gbp,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )


@pytest.fixture
def card(plan: RatePlan) -> RateCard:
    return RateCard.objects.create(plan=plan, name="Default", sort_order=0)


@pytest.fixture
def rate_rule(card: RateCard) -> RateRule:
    return RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )


@pytest.fixture
def guest(db: None) -> Guest:
    return Guest.objects.create(
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )


@pytest.fixture
def terms(db: None) -> TermsVersion:
    return TermsVersion.objects.create(
        version="2026-01",
        body_markdown="**T&Cs**",
        published_at=timezone.now(),
        is_current=True,
    )


@pytest.fixture
def quotation_line(
    guest: Guest,
    gbp: Currency,
    terms: TermsVersion,
    property_: Property,
) -> QuotationLine:
    person = person_for_guest(guest)
    quotation = Quotation.objects.create(
        enquiry=guest.enquiries.create(person=person),
        guest=guest,
        person=person,
        expires_at=timezone.now() + timedelta(days=7),
        terms_version=terms,
    )
    return QuotationLine.objects.create(
        quotation=quotation,
        property=property_,
        currency=gbp,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 17),
        adults=2,
        total=Decimal("1400.00"),
    )
