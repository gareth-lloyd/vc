"""API tests for /properties/{id}/finance — including bank-secret masking."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from properties.enums import CommissionCalcType
from properties.models import GroupFinance, Property, PropertyFinance, PropertyGroup


@pytest.mark.django_db
def test_get_finance_creates_row_when_missing(
    api_client: APIClient, staff: User, property_: Property, group: PropertyGroup
) -> None:
    GroupFinance.objects.get_or_create(group=group)
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/finance")
    assert response.status_code == 200, response.content
    assert PropertyFinance.objects.filter(property=property_).exists()


@pytest.mark.django_db
def test_finance_get_does_not_echo_bank_secrets(
    api_client: APIClient, staff: User, property_: Property, group: PropertyGroup
) -> None:
    GroupFinance.objects.get_or_create(group=group)
    PropertyFinance.objects.create(
        property=property_,
        bank_account_number="123456",
        bank_sort_code="22-33-44",
        bank_iban="GB29NWBK60161331926819",
        bank_bic="NWBKGB2L",
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/finance")
    payload = response.json()
    for field in ("bank_account_number", "bank_sort_code", "bank_iban", "bank_bic"):
        assert field not in payload, f"{field} should be masked in GET response"


@pytest.mark.django_db
def test_patch_finance_updates_commission(
    api_client: APIClient, staff: User, property_: Property, group: PropertyGroup
) -> None:
    GroupFinance.objects.get_or_create(group=group)
    PropertyFinance.objects.create(property=property_)
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/finance",
        data={
            "commission_calculation_type": CommissionCalcType.PERCENT.value,
            "commission_amount": "12.50",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    finance = PropertyFinance.objects.get(property=property_)
    assert finance.commission_amount == Decimal("12.50")
