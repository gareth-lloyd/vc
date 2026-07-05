"""Tests for the `PropertyDefaults` singleton + `GET/PATCH /property-defaults`.

GAP-070: global create-time defaults replacing the per-group
`GroupSettings`/`GroupFinance` floor. One row (`pk=1`), seeded by migration
with the GAP-068 confirmed starter set.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from pricing.models import Currency
from properties.enums import (
    AvailabilityDefault,
    CommissionCalcType,
    DepositCalcType,
    PrefilledChangeOverDay,
    PriceBasis,
    SecurityDepositCalcType,
)
from properties.models import PropertyDefaults

URL = "/api/v1/property-defaults"


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.mark.django_db
def test_get_solo_returns_singleton_pk_1() -> None:
    obj = PropertyDefaults.get_solo()
    assert obj.pk == 1
    # Repeat access returns the same row, never a second one.
    again = PropertyDefaults.get_solo()
    assert again.pk == 1
    assert PropertyDefaults.objects.count() == 1


@pytest.mark.django_db
def test_save_pins_pk_1() -> None:
    # Even if the pk is tampered with, save() re-pins to 1 — a second row can
    # never appear (same guard as core.SystemSettings).
    obj = PropertyDefaults.get_solo()
    obj.pk = None
    obj.hold_duration_hours = 72
    obj.save()
    assert obj.pk == 1
    assert PropertyDefaults.objects.count() == 1
    assert PropertyDefaults.get_solo().hold_duration_hours == 72


@pytest.mark.django_db
def test_seeded_with_gap068_confirmed_set() -> None:
    """Migration seeds the GAP-068 starter set; unlisted fields keep the old
    Group* model defaults; currency stays null until the operator sets it."""
    # The row must ALREADY exist from migration 0026's seed — get_solo() would
    # lazily recreate it and mask a broken/dropped RunPython seed.
    assert PropertyDefaults.objects.filter(pk=1).exists()
    obj = PropertyDefaults.get_solo()
    assert obj.check_in_time == time(16, 30)
    assert obj.check_out_time == time(10, 30)
    assert obj.deposit_required is True
    assert obj.deposit_calculation_type == DepositCalcType.PERCENT
    assert obj.deposit_amount == Decimal("30")
    assert obj.security_deposit_required is True
    assert obj.security_deposit_calculation_type == SecurityDepositCalcType.FIXED
    assert obj.commission_calculation_type == CommissionCalcType.PERCENT
    # Old GroupSettings model defaults carried over.
    assert obj.availability_default == AvailabilityDefault.AVAILABLE
    assert obj.changeover_day == PrefilledChangeOverDay.ANY
    assert obj.min_nights_rental == 1
    assert obj.prices_entered_as == PriceBasis.GROSS
    assert obj.hold_duration_hours == 48
    assert obj.bookings_require_pre_approval is False
    assert obj.currency is None


@pytest.mark.django_db
def test_get_requires_staff(api_client: APIClient) -> None:
    response = api_client.get(URL)
    assert response.status_code == 403


@pytest.mark.django_db
def test_get_allows_any_staff_role(api_client: APIClient, viewer: User) -> None:
    api_client.force_login(viewer)
    response = api_client.get(URL)
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["deposit_amount"] == "30.00"
    assert data["check_in_time"] == "16:30:00"
    assert data["currency"] is None


@pytest.mark.django_db
def test_patch_forbidden_for_viewer(api_client: APIClient, viewer: User) -> None:
    api_client.force_login(viewer)
    response = api_client.patch(URL, data={"hold_duration_hours": 24}, format="json")
    assert response.status_code == 403


@pytest.mark.django_db
def test_patch_updates_singleton(api_client: APIClient, staff: User, gbp: Currency) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        URL,
        data={"hold_duration_hours": 24, "deposit_amount": "25.00", "currency": gbp.pk},
        format="json",
    )
    assert response.status_code == 200, response.content
    obj = PropertyDefaults.get_solo()
    assert obj.hold_duration_hours == 24
    assert obj.deposit_amount == Decimal("25.00")
    assert obj.currency == gbp


@pytest.mark.django_db
def test_post_and_delete_not_allowed(api_client: APIClient, staff: User) -> None:
    api_client.force_login(staff)
    assert api_client.post(URL, data={}, format="json").status_code == 405
    assert api_client.delete(URL).status_code == 405
