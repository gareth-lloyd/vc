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


@pytest.mark.django_db
def test_create_extra_defaults_to_commissionable(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/extras",
        {
            "name": "Chef",
            "kind": ExtraKind.OTHER,
            "calc": ExtraCalc.FIXED_PER_STAY,
            "amount": "1000.00",
            "currency": gbp.pk,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["commissionable"] is True
    assert Extra.objects.get(pk=payload["id"]).commissionable is True


@pytest.mark.django_db
def test_create_non_commissionable_extra_round_trips(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/extras",
        {
            "name": "Chef",
            "kind": ExtraKind.OTHER,
            "calc": ExtraCalc.FIXED_PER_STAY,
            "amount": "1000.00",
            "currency": gbp.pk,
            "commissionable": False,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["commissionable"] is False
    assert Extra.objects.get(pk=payload["id"]).commissionable is False


@pytest.mark.django_db
def test_patch_extra_commissionable(
    api_client: APIClient,
    staff: User,
    extra: Extra,
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/extras/{extra.pk}",
        {"commissionable": False},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["commissionable"] is False
    extra.refresh_from_db()
    assert extra.commissionable is False


@pytest.mark.django_db
def test_list_extras_filters_on_commissionable(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    extra: Extra,
) -> None:
    non_comm = Extra.objects.create(
        property=property_,
        name="Chef",
        kind=ExtraKind.OTHER,
        calc=ExtraCalc.FIXED_PER_STAY,
        amount=Decimal("1000.00"),
        currency=gbp,
        commissionable=False,
    )
    api_client.force_login(staff)
    response = api_client.get(
        f"/api/v1/properties/{property_.pk}/extras",
        {"commissionable": "false"},
    )
    assert response.status_code == 200, response.content
    ids = [r["id"] for r in response.json()["results"]]
    assert ids == [non_comm.pk]
