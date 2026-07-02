"""Create-contract tests for `/properties/{id}/extras` and `/properties/{id}/discounts`.

These POST the byte-exact wire payloads the workbench dialogs send
(`ExtraFormDialog.toPayload` / `DiscountFormDialog.toPayload`) — no `property`
key, nulls included — rather than hand-picked field subsets.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, cast

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.enums import RuleKind
from pricing.factories import DiscountFactory, ExtraFactory
from pricing.models import Currency, Discount, Extra
from properties.factories import PropertyFactory

if TYPE_CHECKING:
    from properties.models import Property


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="create-contract@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def api_client(staff: User) -> APIClient:
    client = APIClient()
    client.force_login(staff)
    return client


@pytest.fixture
def other_property(db: None) -> Property:
    from properties.models import Property as PropertyModel

    return cast(PropertyModel, PropertyFactory())


def extra_wire_payload(currency: Currency) -> dict[str, object]:
    """Exactly what `ExtraFormDialog.toPayload` sends on create."""
    return {
        "name": "Mid-stay clean",
        "description": "",
        "kind": "cleaning",
        "calc": "fixed_per_stay",
        "amount": "120.00",
        "currency": currency.pk,
        "is_mandatory": False,
        "applies_from": None,
        "applies_to": None,
        "is_active": True,
    }


def discount_wire_payload() -> dict[str, object]:
    """Exactly what `DiscountFormDialog.toPayload` sends on create."""
    return {
        "name": "Early bird 10%",
        "code": None,
        "rule_kind": "early_bird",
        "kind": "percent",
        "amount": "10.00",
        "min_nights": None,
        "threshold_days": None,
        "valid_from": "2026-01-01",
        "valid_to": "2026-12-31",
        "max_uses": None,
        "is_active": True,
    }


@pytest.mark.django_db
def test_create_extra_with_fe_wire_payload(
    api_client: APIClient, property_: Property, gbp: Currency
) -> None:
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/extras",
        extra_wire_payload(gbp),
        format="json",
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["property"] == property_.pk
    extra = Extra.objects.get(pk=payload["id"])
    assert extra.property_id == property_.pk
    assert extra.amount == Decimal("120.00")


@pytest.mark.django_db
def test_create_extra_body_property_is_ignored(
    api_client: APIClient,
    property_: Property,
    other_property: Property,
    gbp: Currency,
) -> None:
    body = extra_wire_payload(gbp) | {"property": other_property.pk}
    response = api_client.post(f"/api/v1/properties/{property_.pk}/extras", body, format="json")
    assert response.status_code == 201, response.content
    assert response.json()["property"] == property_.pk


@pytest.mark.django_db
def test_create_extra_inverted_applies_range_is_400_not_500(
    api_client: APIClient, property_: Property, gbp: Currency
) -> None:
    body = extra_wire_payload(gbp) | {"applies_from": "2026-06-01", "applies_to": "2026-01-01"}
    response = api_client.post(f"/api/v1/properties/{property_.pk}/extras", body, format="json")
    assert response.status_code == 400, response.content
    assert "applies_to" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_discount_with_fe_wire_payload(api_client: APIClient, property_: Property) -> None:
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/discounts",
        discount_wire_payload(),
        format="json",
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["property"] == property_.pk
    # `min_nights: null` on the wire is tolerated and stored as the model
    # default 0 (the column is NOT NULL).
    assert payload["min_nights"] == 0
    discount = Discount.objects.get(pk=payload["id"])
    assert discount.min_nights == 0
    assert discount.threshold_days is None
    assert discount.max_uses is None
    assert discount.code is None


@pytest.mark.django_db
def test_create_discount_body_property_is_ignored(
    api_client: APIClient, property_: Property, other_property: Property
) -> None:
    body = discount_wire_payload() | {"property": other_property.pk}
    response = api_client.post(f"/api/v1/properties/{property_.pk}/discounts", body, format="json")
    assert response.status_code == 201, response.content
    assert response.json()["property"] == property_.pk


@pytest.mark.django_db
def test_create_discount_blank_code_is_stored_as_null(
    api_client: APIClient, property_: Property
) -> None:
    body = discount_wire_payload() | {"code": ""}
    response = api_client.post(f"/api/v1/properties/{property_.pk}/discounts", body, format="json")
    assert response.status_code == 201, response.content
    assert Discount.objects.get(pk=response.json()["id"]).code is None


@pytest.mark.django_db
def test_create_discount_inverted_validity_range_is_rejected(
    api_client: APIClient, property_: Property
) -> None:
    body = discount_wire_payload() | {"valid_from": "2026-12-31", "valid_to": "2026-01-01"}
    response = api_client.post(f"/api/v1/properties/{property_.pk}/discounts", body, format="json")
    assert response.status_code == 400, response.content
    assert "valid_to" in response.json()["field_errors"]


@pytest.mark.django_db
def test_global_discount_create_is_not_allowed(api_client: APIClient, property_: Property) -> None:
    body = discount_wire_payload() | {"property": property_.pk}
    response = api_client.post("/api/v1/discounts", body, format="json")
    assert response.status_code == 405, response.content


@pytest.fixture
def discount(property_: Property) -> Discount:
    return cast(
        Discount, DiscountFactory(property=property_, rule_kind=RuleKind.PROMO_CODE, min_nights=3)
    )


@pytest.fixture
def extra(property_: Property, gbp: Currency) -> Extra:
    return cast(Extra, ExtraFactory(property=property_, currency=gbp))


@pytest.mark.django_db
def test_patch_extra_property_is_immutable(
    api_client: APIClient, extra: Extra, other_property: Property
) -> None:
    response = api_client.patch(
        f"/api/v1/extras/{extra.pk}",
        {"name": "Deep clean", "property": other_property.pk},
        format="json",
    )
    assert response.status_code == 200, response.content
    extra.refresh_from_db()
    assert extra.name == "Deep clean"
    assert extra.property_id != other_property.pk


@pytest.mark.django_db
def test_patch_discount_property_is_immutable(
    api_client: APIClient, discount: Discount, other_property: Property
) -> None:
    response = api_client.patch(
        f"/api/v1/discounts/{discount.pk}",
        {"name": "Renamed promo", "property": other_property.pk},
        format="json",
    )
    assert response.status_code == 200, response.content
    discount.refresh_from_db()
    assert discount.name == "Renamed promo"
    assert discount.property_id != other_property.pk


@pytest.mark.django_db
def test_patch_discount_min_nights_null_coerces_to_zero(
    api_client: APIClient, discount: Discount
) -> None:
    response = api_client.patch(
        f"/api/v1/discounts/{discount.pk}",
        {"min_nights": None},
        format="json",
    )
    assert response.status_code == 200, response.content
    discount.refresh_from_db()
    assert discount.min_nights == 0
