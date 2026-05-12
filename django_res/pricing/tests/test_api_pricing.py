"""API tests for /pricing:quote, /pricing:quote-bulk, /discounts:lookup-code."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.enums import StaffRole
from accounts.models import User
from pricing.enums import DiscountKind, RuleKind
from pricing.models import Currency, Discount, RateRule
from properties.models import Property


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="pricing@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_pricing_quote_happy_path(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateRule,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/pricing:quote",
        data={
            "property_id": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 4,
            "currency": "GBP",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["total"] == "1400.00"
    assert len(body["lines"]) == 7


@pytest.mark.django_db
def test_pricing_quote_bulk_returns_all_requests(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateRule,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/pricing:quote-bulk",
        data={
            "currency": "GBP",
            "requests": [
                {
                    "property_id": property_.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 4,
                },
                {
                    "property_id": property_.pk,
                    "date_from": "2026-07-01",
                    "date_to": "2026-07-08",
                    "adults": 4,
                },
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    quotes = response.json()["quotes"]
    assert len(quotes) == 2
    assert all(q["available"] for q in quotes)


@pytest.mark.django_db
def test_discount_lookup_code_happy(
    api_client: APIClient,
    staff: User,
    property_: Property,
) -> None:
    Discount.objects.create(
        property=property_,
        name="Welcome 10",
        code="WELCOME10",
        rule_kind=RuleKind.PROMO_CODE.value,
        kind=DiscountKind.PERCENT.value,
        amount=Decimal("10"),
        valid_from=date(2026, 1, 1),
        valid_to=date(2026, 12, 31),
        is_active=True,
    )
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/discounts:lookup-code",
        data={
            "property_id": property_.pk,
            "code": "WELCOME10",
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["applies"] is True
    assert body["kind"] == DiscountKind.PERCENT.value


@pytest.mark.django_db
def test_discount_lookup_code_not_found(
    api_client: APIClient,
    staff: User,
    property_: Property,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/discounts:lookup-code",
        data={
            "property_id": property_.pk,
            "code": "DOESNOTEXIST",
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
        },
        format="json",
    )
    assert response.status_code == 404
