"""Pricing test fixtures.

Builds a minimal property graph (category + region + country +
property) so tests don't need to know the full `properties` schema.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from pricing.models import Currency, RateBand, RatePeriod, RatePlan

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
        Region,
    )

    country, _ = Country.objects.get_or_create(
        iso2="GB",
        defaults={"name": "United Kingdom", "iso3": "GBR"},
    )
    region = Region.objects.create(country=country, name="South West", slug="south-west")
    category = PropertyCategory.objects.create(name="Villa", slug="villa")
    return Property.objects.create(
        name="Test Villa",
        display_name="Test Villa",
        slug="test-villa",
        category=category,
        region=region,
    )


@pytest.fixture
def plan(property_: Property, gbp: Currency) -> RatePlan:
    # Occupancy-capable by default: most pricing tests exercise multi-band
    # (party-bracket) pricing, which a flat plan forbids. The flat mode has its
    # own `flat_plan` / `flat_period` fixtures below.
    return RatePlan.objects.create(
        property=property_,
        name="Summer 2026",
        currency=gbp,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        prices_by_occupancy=True,
    )


@pytest.fixture
def period(plan: RatePlan) -> RatePeriod:
    return RatePeriod.objects.create(
        plan=plan,
        name="Summer",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
    )


@pytest.fixture
def future_period(plan: RatePlan) -> RatePeriod:
    """A never-historical period for tests that mutate a stored period through
    the API and expect success — the elapsed-period guard (GAP historical lock)
    rejects edits to any period whose ``date_to`` is before today, so a
    2026-dated fixture would rot once the wall clock passes it. 2099 keeps these
    clock-independent. Disjoint from the shared ``period`` (same plan)."""
    return RatePeriod.objects.create(
        plan=plan,
        name="Future",
        date_from=date(2099, 6, 1),
        date_to=date(2099, 8, 31),
    )


@pytest.fixture
def flat_plan(property_: Property, gbp: Currency) -> RatePlan:
    """A flat-rate plan (party size ignored): one band per period, no occupancy."""
    return RatePlan.objects.create(
        property=property_,
        name="Flat 2026",
        currency=gbp,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        prices_by_occupancy=False,
    )


@pytest.fixture
def flat_period(flat_plan: RatePlan) -> RatePeriod:
    return RatePeriod.objects.create(
        plan=flat_plan,
        name="All year",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
    )


@pytest.fixture
def rule(period: RatePeriod) -> RateBand:
    return RateBand.objects.create(
        period=period,
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )
