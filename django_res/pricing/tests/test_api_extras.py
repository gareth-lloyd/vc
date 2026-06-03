"""API tests for `/properties/{id}/extras` + `/extras/{id}` CRUD."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.enums import ExtraCalc, ExtraKind
from pricing.models import Currency, Extra
from properties.models import Property


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="extras@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def extra(property_: Property, gbp: Currency) -> Extra:
    return Extra.objects.create(
        property=property_,
        name="Cleaning",
        kind=ExtraKind.CLEANING,
        calc=ExtraCalc.FIXED_PER_STAY,
        amount=Decimal("150.00"),
        currency=gbp,
    )


@pytest.mark.django_db
def test_list_extras_exposes_currency_code(
    api_client: APIClient,
    staff: User,
    property_: Property,
    extra: Extra,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/extras")
    assert response.status_code == 200, response.content
    payload = response.json()
    row = next(r for r in payload["results"] if r["id"] == extra.pk)
    assert row["currency"] == extra.currency_id
    assert row["currency_code"] == extra.currency.code


@pytest.mark.django_db
def test_extra_detail_exposes_currency_code(
    api_client: APIClient,
    staff: User,
    extra: Extra,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/extras/{extra.pk}")
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["currency"] == extra.currency_id
    assert payload["currency_code"] == extra.currency.code
