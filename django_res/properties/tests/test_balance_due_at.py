"""Tests for Property.balance_due_at()."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from properties.models import Property, PropertyFinance


@pytest.fixture
def finance(property_: Property) -> PropertyFinance:
    return PropertyFinance.objects.create(
        property=property_,
        days_balance_due_before_arrival=42,
    )


@pytest.mark.django_db
def test_happy_path(property_: Property, finance: PropertyFinance) -> None:
    assert property_.balance_due_at(date(2026, 8, 1)) == date(2026, 8, 1) - timedelta(days=42)


@pytest.mark.django_db
def test_null_date_from(property_: Property, finance: PropertyFinance) -> None:
    assert property_.balance_due_at(None) is None


@pytest.mark.django_db
def test_no_finance(property_: Property) -> None:
    assert property_.balance_due_at(date(2026, 8, 1)) is None


@pytest.mark.django_db
def test_null_days_falls_back_to_policy_floor(property_: Property) -> None:
    """PropertyFinance with NULL days resolves to the policy floor (60)."""
    PropertyFinance.objects.create(
        property=property_,
        days_balance_due_before_arrival=None,
    )
    assert property_.balance_due_at(date(2026, 8, 1)) == date(2026, 8, 1) - timedelta(days=60)
