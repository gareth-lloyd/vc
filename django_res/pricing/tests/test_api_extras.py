"""API tests for `/properties/{id}/extras` + `/extras/{id}` CRUD."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.enums import ExtraCalc, ExtraKind
from pricing.models import Currency, Extra
from properties.factories import PropertyFactory
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


# ---------------------------------------------------------------------------
# SMELL-009: `:duplicate` characterisation (endpoint had zero coverage)
# ---------------------------------------------------------------------------


@pytest.fixture
def rich_extra(property_: Property, gbp: Currency) -> Extra:
    """Non-default values on every copyable field, so the field-list
    assertion below can catch a silently dropped column."""
    return Extra.objects.create(
        property=property_,
        name="Heated pool",
        description="Pool heating, per week",
        kind=ExtraKind.OTHER,
        calc=ExtraCalc.FIXED_PER_NIGHT,
        amount=Decimal("350.00"),
        currency=gbp,
        is_mandatory=False,
        commissionable=False,
        applies_from=date(2026, 5, 1),
        applies_to=date(2026, 9, 30),
        min_party=2,
        max_party=10,
        sort_order=7,
        is_active=False,
        notes="owner insists",
    )


@pytest.mark.django_db
def test_extra_duplicate_copies_every_field(
    api_client: APIClient,
    staff: User,
    rich_extra: Extra,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/extras/{rich_extra.pk}:duplicate")
    assert response.status_code == 201, response.content

    clone = Extra.objects.get(pk=response.json()["id"])
    assert clone.pk != rich_extra.pk
    assert clone.property_id == rich_extra.property_id
    assert clone.name == "Heated pool (copy)"
    assert clone.description == "Pool heating, per week"
    assert clone.kind == ExtraKind.OTHER
    assert clone.calc == ExtraCalc.FIXED_PER_NIGHT
    assert clone.amount == Decimal("350.00")
    assert clone.currency_id == rich_extra.currency_id
    assert clone.is_mandatory is False
    assert clone.commissionable is False
    assert clone.applies_from == date(2026, 5, 1)
    assert clone.applies_to == date(2026, 9, 30)
    assert (clone.min_party, clone.max_party) == (2, 10)
    assert clone.sort_order == 7
    assert clone.is_active is False
    assert clone.notes == "owner insists"


@pytest.mark.django_db
def test_extra_duplicate_reparents_to_target_property(
    api_client: APIClient,
    staff: User,
    rich_extra: Extra,
) -> None:
    target = cast(Property, PropertyFactory())
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/extras/{rich_extra.pk}:duplicate",
        data={"target_property_id": target.pk},
        format="json",
    )
    assert response.status_code == 201, response.content
    clone = Extra.objects.get(pk=response.json()["id"])
    assert clone.property_id == target.pk
    assert clone.name == "Heated pool (copy)"
    # The source row is untouched.
    rich_extra.refresh_from_db()
    assert rich_extra.property_id != target.pk


@pytest.mark.django_db
def test_extra_duplicate_unknown_target_is_404(
    api_client: APIClient,
    staff: User,
    extra: Extra,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/extras/{extra.pk}:duplicate",
        data={"target_property_id": 999999},
        format="json",
    )
    assert response.status_code == 404, response.content


@pytest.mark.django_db
def test_extra_duplicate_without_body_clones_in_place(
    api_client: APIClient,
    staff: User,
    extra: Extra,
) -> None:
    api_client.force_login(staff)
    first = api_client.post(f"/api/v1/extras/{extra.pk}:duplicate")
    second = api_client.post(f"/api/v1/extras/{extra.pk}:duplicate")
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert Extra.objects.filter(name="Cleaning (copy)").count() == 2
