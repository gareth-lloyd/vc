"""Pricing test fixtures.

Builds a minimal property graph (category + group + region + country +
property) so tests don't need to know the full `properties` schema.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from pricing.models import Currency, RateCard, RatePlan, RateRule

if TYPE_CHECKING:
    from properties.models import Property


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.fixture
def usd(db: None) -> Currency:
    return Currency.objects.create(code="USD", name="US dollar", symbol="$")


@pytest.fixture
def property_(db: None) -> Property:
    """Build a minimal `properties.Property` chain for use in pricing tests."""
    from properties.models import (
        Country,
        Property,
        PropertyCategory,
        PropertyGroup,
        Region,
    )

    country = Country.objects.create(name="United Kingdom", iso2="GB", iso3="GBR")
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
def rule(card: RateCard) -> RateRule:
    return RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )
