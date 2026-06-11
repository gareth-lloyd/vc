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
        is_staff=True,
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
def test_pricing_quote_bulk_surfaces_plan_card_metadata(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateRule,
) -> None:
    """Priced bulk entries carry the breakdown's plan/card metadata so the
    quote builder can render information-dense result lines."""
    plan = rule.card.plan
    plan.inclusion = "Daily maid service"
    plan.save(update_fields=["inclusion"])

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
                }
            ],
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    entry = response.json()["quotes"][0]
    assert entry["inclusion"] == "Daily maid service"
    assert entry["changeover_day"] is None
    assert entry["min_nights"] == 1
    assert entry["max_nights"] is None
    assert entry["occupancy_pricing"] is False


@pytest.mark.django_db
def test_pricing_quote_without_currency_prices_in_plan_currency(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateRule,
) -> None:
    """GAP-014: currency omitted → priced in the rate plan's own currency."""
    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/pricing:quote",
        data={
            "property_id": property_.pk,
            "date_from": "2026-06-10",
            "date_to": "2026-06-17",
            "adults": 4,
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["currency_code"] == "GBP"
    assert body["total"] == "1400.00"


@pytest.mark.django_db
def test_pricing_quote_bulk_mixed_currencies_all_price(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateRule,
) -> None:
    """GAP-014: a currency-less bulk quote prices a GBP villa and an EUR villa
    in one batch — no `no_rate_available` from currency mismatch."""
    from pricing.models import RateCard, RatePlan
    from pricing.models import RateRule as RR

    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    eur_villa = Property.objects.create(
        name="EUR Villa",
        display_name="EUR Villa",
        slug="eur-villa",
        category=property_.category,
        group=property_.group,
        region=property_.region,
    )
    plan2 = RatePlan.objects.create(
        property=eur_villa,
        name="Summer 2026",
        currency=eur,
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
        nightly=Decimal("300.00"),
    )

    api_client.force_login(staff)
    response = api_client.post(
        "/api/v1/pricing:quote-bulk",
        data={
            "requests": [
                {
                    "property_id": property_.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 4,
                },
                {
                    "property_id": eur_villa.pk,
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
    assert by_id[property_.pk]["currency_code"] == "GBP"
    assert by_id[eur_villa.pk]["available"] is True
    assert by_id[eur_villa.pk]["currency_code"] == "EUR"


@pytest.mark.django_db
def test_pricing_quote_unknown_explicit_currency_404s(
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
            "currency": "XXX",
        },
        format="json",
    )
    assert response.status_code == 404


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
def test_quote_bulk_no_rate_entry_carries_image_and_currency(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateRule,
) -> None:
    """Q-013: an unpriceable property's bulk entry must carry enough for the
    manual-quote affordance — the no-rate flag, the hero image (card parity
    with priced siblings), and the resolved currency the operator will type
    a manual total against."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from properties.enums import ImageKind
    from properties.models import PropertyImage

    PropertyImage.objects.create(
        property=property_,
        kind=ImageKind.HERO,
        image=SimpleUploadedFile("hero.jpg", b"x", content_type="image/jpeg"),
    )

    api_client.force_login(staff)
    # September is inside the rate plan but outside the only rule (Jun-Aug).
    response = api_client.post(
        "/api/v1/pricing:quote-bulk",
        data={
            "requests": [
                {
                    "property_id": property_.pk,
                    "date_from": "2026-09-10",
                    "date_to": "2026-09-17",
                    "adults": 4,
                },
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    (quote,) = response.json()["quotes"]
    assert quote["available"] is False
    assert quote["error_code"] == "no_rate_available"
    assert quote["hero_image_url"] is not None
    assert ".jpg" in quote["hero_image_url"]
    assert quote["currency_code"] == "GBP"


@pytest.mark.django_db
def test_quote_bulk_other_errors_skip_currency_resolution(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateRule,
) -> None:
    """Only no-rate entries feed the manual-quote card, so only they pay the
    currency-resolution queries; other error codes carry a null currency_code
    (and keep the prefetched image for the collapsed list's thumbnails)."""
    api_client.force_login(staff)
    # Party of 20 exceeds the rule's max_party=8 -> party_out_of_range.
    response = api_client.post(
        "/api/v1/pricing:quote-bulk",
        data={
            "requests": [
                {
                    "property_id": property_.pk,
                    "date_from": "2026-06-10",
                    "date_to": "2026-06-17",
                    "adults": 20,
                },
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    (quote,) = response.json()["quotes"]
    assert quote["available"] is False
    assert quote["error_code"] == "party_out_of_range"
    assert quote["currency_code"] is None
    assert quote["hero_image_url"] is None  # property has no HERO image here


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
