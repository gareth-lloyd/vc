"""Creation-time snapshot of `PropertyDefaults` (GAP-070 unit 2).

Creating a property (API create or `:duplicate`) materialises concrete
`PropertySettings`/`PropertyFinance` rows copied from the global singleton.
After creation they are plain attributes — changing a global default never
touches an existing property.
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from pricing.models import Currency
from properties.enums import DepositCalcType, PriceBasis, SecurityDepositCalcType
from properties.models import (
    Property,
    PropertyCategory,
    PropertyDefaults,
    PropertyFinance,
    PropertySettings,
    Region,
)
from properties.services.defaults import snapshot_defaults


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.mark.django_db
def test_snapshot_defaults_copies_settings_and_finance(property_: Property, gbp: Currency) -> None:
    defaults = PropertyDefaults.get_solo()
    defaults.currency = gbp
    defaults.hold_duration_hours = 24
    defaults.deposit_amount = Decimal("40")
    defaults.save()

    snapshot_defaults(property_)

    settings = PropertySettings.objects.get(property=property_)
    assert settings.currency == gbp
    assert settings.hold_duration_hours == 24
    assert settings.check_in_time == time(16, 30)
    assert settings.check_out_time == time(10, 30)
    assert settings.prices_entered_as == PriceBasis.GROSS
    assert settings.min_nights_rental == 1

    finance = PropertyFinance.objects.get(property=property_)
    assert finance.deposit_required is True
    assert finance.deposit_calculation_type == DepositCalcType.PERCENT
    assert finance.deposit_amount == Decimal("40")
    assert finance.security_deposit_required is True
    assert finance.security_deposit_calculation_type == SecurityDepositCalcType.FIXED
    # Per-owner fields are never defaulted globally.
    assert finance.contact is None
    assert finance.bank_account_name == ""
    assert finance.tax_number == ""


@pytest.mark.django_db
def test_snapshot_defaults_never_clobbers_existing_rows(property_: Property) -> None:
    PropertySettings.objects.create(property=property_, hold_duration_hours=99)
    PropertyFinance.objects.create(property=property_, deposit_amount=Decimal("77"))

    snapshot_defaults(property_)

    assert PropertySettings.objects.get(property=property_).hold_duration_hours == 99
    assert PropertyFinance.objects.get(property=property_).deposit_amount == Decimal("77")


@pytest.mark.django_db
def test_api_create_snapshots_defaults(
    api_client: APIClient,
    staff: User,
    category: PropertyCategory,
    region: Region,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/properties",
        data={
            "name": "Snapshot Villa",
            "display_name": "Snapshot Villa",
            "slug": "snapshot-villa",
            "category": category.pk,
            "region": region.pk,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    prop = Property.objects.get(slug="snapshot-villa")
    settings = PropertySettings.objects.get(property=prop)
    assert settings.check_in_time == time(16, 30)
    assert settings.hold_duration_hours == 48
    finance = PropertyFinance.objects.get(property=prop)
    assert finance.deposit_amount == Decimal("30")


@pytest.mark.django_db
def test_changing_global_default_does_not_touch_existing_property(
    property_: Property,
) -> None:
    snapshot_defaults(property_)
    defaults = PropertyDefaults.get_solo()
    defaults.deposit_amount = Decimal("999")
    defaults.hold_duration_hours = 1
    defaults.save()

    settings = PropertySettings.objects.get(property=property_)
    finance = PropertyFinance.objects.get(property=property_)
    assert settings.hold_duration_hours == 48
    assert finance.deposit_amount == Decimal("30")


@pytest.mark.django_db
def test_duplicate_snapshots_defaults_for_clone(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    # Customise the ORIGINAL first: the clone must get the GLOBAL defaults,
    # not a copy of the original's settings/finance (docstring contract).
    PropertySettings.objects.create(property=property_, hold_duration_hours=99)
    PropertyFinance.objects.create(property=property_, deposit_amount=Decimal("77"))

    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/properties/{property_.pk}:duplicate")
    assert response.status_code == 201, response.content
    clone = Property.objects.get(slug=f"{property_.slug}-copy")
    clone_settings = PropertySettings.objects.get(property=clone)
    clone_finance = PropertyFinance.objects.get(property=clone)
    assert clone_settings.hold_duration_hours == 48
    assert clone_finance.deposit_amount == Decimal("30")
    assert clone_finance.deposit_required is True
