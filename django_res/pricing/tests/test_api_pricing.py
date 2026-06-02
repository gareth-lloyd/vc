"""API tests for /pricing:quote, /pricing:quote-bulk, /discounts:lookup-code."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
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


@pytest.mark.django_db
def test_quote_bulk_carries_hero_image_url(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateRule,
) -> None:
    """Each available bulk quote carries hero_image_url (str for HERO, null otherwise)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from pricing.models import RateCard, RatePlan
    from pricing.models import RateRule as RR
    from properties.enums import ImageKind
    from properties.models import Property, PropertyImage

    PropertyImage.objects.create(
        property=property_,
        kind=ImageKind.HERO,
        image=SimpleUploadedFile("hero.jpg", b"x", content_type="image/jpeg"),
    )

    # A second priceable property with no HERO image.
    no_hero = Property.objects.create(
        name="No Hero Villa",
        display_name="No Hero Villa",
        slug="no-hero-villa",
        category=property_.category,
        group=property_.group,
        region=property_.region,
    )
    plan2 = RatePlan.objects.create(
        property=no_hero,
        name="Summer 2026",
        currency=gbp,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    card2 = RateCard.objects.create(plan=plan2, name="Default", sort_order=0)
    RR.objects.create(
        card=card2,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )

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
                    "property_id": no_hero.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 4,
                },
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    by_id = {q["property_id"]: q for q in response.json()["quotes"]}
    assert by_id[property_.pk]["available"] is True
    assert by_id[property_.pk]["hero_image_url"] is not None
    assert ".jpg" in by_id[property_.pk]["hero_image_url"]
    assert by_id[no_hero.pk]["hero_image_url"] is None
