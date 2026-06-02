"""API tests for /seasons, /rate-cards, /rules CRUD + duplicate action."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.models import Currency, RateCard, RatePlan, RateRule
from properties.models import Property


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        email="seasons@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_list_seasons_for_property(
    api_client: APIClient,
    staff: User,
    property_: Property,
    plan: RatePlan,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/seasons")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    row = next(r for r in payload["results"] if r["id"] == plan.pk)
    assert row["currency"] == plan.currency_id
    assert row["currency_code"] == plan.currency.code


@pytest.mark.django_db
def test_season_detail_exposes_currency_code(
    api_client: APIClient,
    staff: User,
    plan: RatePlan,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/seasons/{plan.pk}")
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["currency"] == plan.currency_id
    assert payload["currency_code"] == plan.currency.code


@pytest.mark.django_db
def test_create_season(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/seasons",
        data={
            "name": "Winter 2027",
            "currency": gbp.pk,
            "effective_from": "2027-01-01",
            "effective_to": "2027-03-31",
            "is_active": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert RatePlan.objects.filter(name="Winter 2027").exists()


@pytest.mark.django_db
def test_season_duplicate_copies_cards_and_rules(
    api_client: APIClient,
    staff: User,
    plan: RatePlan,
    card: RateCard,
    rule: RateRule,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/seasons/{plan.pk}:duplicate")
    assert response.status_code == 201, response.content
    payload = response.json()
    cloned = RatePlan.objects.get(pk=payload["id"])
    assert cloned.cards.count() == 1
    first_card = cloned.cards.first()
    assert first_card is not None
    assert first_card.rules.count() == 1


@pytest.mark.django_db
def test_create_rate_card(api_client: APIClient, staff: User, plan: RatePlan) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/seasons/{plan.pk}/rate-cards",
        data={"name": "Long stay", "min_nights": 7, "sort_order": 1},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert RateCard.objects.filter(plan=plan, name="Long stay").exists()


@pytest.mark.django_db
def test_create_rate_rule(api_client: APIClient, staff: User, card: RateCard) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/rate-cards/{card.pk}/rules",
        data={
            "date_from": "2026-09-01",
            "date_to": "2026-09-30",
            "min_party": 1,
            "max_party": 6,
            "nightly": "180.00",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert RateRule.objects.filter(card=card, nightly=Decimal("180.00")).exists()


@pytest.mark.django_db
def test_get_rate_rule_detail(api_client: APIClient, staff: User, rule: RateRule) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/rules/{rule.pk}")
    assert response.status_code == 200
    assert response.json()["id"] == rule.pk


@pytest.mark.django_db
def test_delete_rate_card(api_client: APIClient, staff: User, card: RateCard) -> None:
    api_client.force_login(staff)
    response = api_client.delete(f"/api/v1/rate-cards/{card.pk}")
    assert response.status_code == 204
    assert not RateCard.objects.filter(pk=card.pk).exists()


@pytest.mark.django_db
def test_season_detail_inlines_cards_with_rules(
    api_client: APIClient,
    staff: User,
    plan: RatePlan,
    card: RateCard,
    rule: RateRule,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/seasons/{plan.pk}")
    assert response.status_code == 200, response.content
    payload = response.json()
    assert "cards" in payload
    assert len(payload["cards"]) == 1
    assert len(payload["cards"][0]["rules"]) == 1


# Touch a couple of variables to silence "unused" complaints from the linter.
_ = (date, Decimal)
