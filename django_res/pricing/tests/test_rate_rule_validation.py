"""Serializer-level validation for RateRule writes.

The four RateRule DB check constraints used to surface as 500
``IntegrityError`` when violated through the API. The serializer now
pre-validates them so the client gets a 400 with ``field_errors`` instead:

* ``date_from`` on or before ``date_to`` (inclusive; single-day allowed — GAP-056),
* ``min_party`` <= ``max_party``,
* at least one of ``nightly`` / ``weekly`` / ``is_poa``,
* ``is_poa`` excludes ``nightly`` / ``weekly``.

PATCH merges the incoming attrs with the stored instance before checking, so
a partial update can't sneak a stored+incoming combination past a constraint.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.models import RateCard, RateRule


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="rule-validation@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def api_client(staff: User) -> APIClient:
    client = APIClient()
    client.force_login(staff)
    return client


def _valid_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "date_from": "2026-06-01",
        "date_to": "2026-06-08",
        "min_party": 1,
        "max_party": 8,
        "nightly": "150.00",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_create_rule_rejects_inverted_date_range(api_client: APIClient, card: RateCard) -> None:
    """An inverted span (date_from after date_to) is rejected."""
    response = api_client.post(
        f"/api/v1/rate-cards/{card.pk}/rules",
        data=_valid_payload(date_from="2026-06-08", date_to="2026-06-01"),
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "date_to" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_single_day_rule_succeeds(api_client: APIClient, card: RateCard) -> None:
    """GAP-056: inclusive dates — date_from == date_to is a valid one-day rule."""
    response = api_client.post(
        f"/api/v1/rate-cards/{card.pk}/rules",
        data=_valid_payload(date_from="2026-06-01", date_to="2026-06-01"),
        format="json",
    )
    assert response.status_code == 201, response.content


@pytest.mark.django_db
def test_create_rule_rejects_min_party_above_max_party(
    api_client: APIClient, card: RateCard
) -> None:
    response = api_client.post(
        f"/api/v1/rate-cards/{card.pk}/rules",
        data=_valid_payload(min_party=9, max_party=2),
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "max_party" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_rule_requires_price_or_poa(api_client: APIClient, card: RateCard) -> None:
    response = api_client.post(
        f"/api/v1/rate-cards/{card.pk}/rules",
        data=_valid_payload(nightly=None),
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "nightly" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_rule_rejects_poa_with_price(api_client: APIClient, card: RateCard) -> None:
    response = api_client.post(
        f"/api/v1/rate-cards/{card.pk}/rules",
        data=_valid_payload(is_poa=True),
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "is_poa" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_poa_only_rule_succeeds(api_client: APIClient, card: RateCard) -> None:
    response = api_client.post(
        f"/api/v1/rate-cards/{card.pk}/rules",
        data=_valid_payload(nightly=None, is_poa=True),
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["is_poa"] is True


@pytest.mark.django_db
def test_patch_poa_onto_priced_rule_rejected_without_clearing_price(
    api_client: APIClient, rule: RateRule
) -> None:
    """Partial update must merge stored attrs: stored nightly + incoming POA clash."""
    response = api_client.patch(
        f"/api/v1/rules/{rule.pk}",
        data={"is_poa": True},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "is_poa" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_poa_onto_priced_rule_succeeds_when_prices_cleared(
    api_client: APIClient, rule: RateRule
) -> None:
    response = api_client.patch(
        f"/api/v1/rules/{rule.pk}",
        data={"is_poa": True, "nightly": None, "weekly": None},
        format="json",
    )
    assert response.status_code == 200, response.content
    rule.refresh_from_db()
    assert rule.is_poa is True
    assert rule.nightly is None


@pytest.mark.django_db
def test_patch_dates_validates_against_stored_counterpart(
    api_client: APIClient, rule: RateRule
) -> None:
    """Moving date_from past the stored date_to must be rejected."""
    assert rule.date_to.isoformat() == "2026-08-31"
    response = api_client.patch(
        f"/api/v1/rules/{rule.pk}",
        data={"date_from": "2026-09-15"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "date_to" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_priced_rule_price_change_succeeds(api_client: APIClient, rule: RateRule) -> None:
    response = api_client.patch(
        f"/api/v1/rules/{rule.pk}",
        data={"nightly": "275.00"},
        format="json",
    )
    assert response.status_code == 200, response.content
    rule.refresh_from_db()
    assert rule.nightly == Decimal("275.00")


@pytest.mark.django_db
def test_create_rule_omitting_defaulted_min_party_still_validates_band(
    api_client: APIClient, card: RateCard
) -> None:
    """Omitted min_party falls back to the model default (1), so max_party=0 clashes."""
    payload = _valid_payload(max_party=0)
    del payload["min_party"]
    response = api_client.post(
        f"/api/v1/rate-cards/{card.pk}/rules",
        data=payload,
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "max_party" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_overlapping_rule_returns_400(api_client: APIClient, rule: RateRule) -> None:
    """Sharing the stored rule's date_to (ranges are inclusive) is an overlap → 400, not 500."""
    response = api_client.post(
        f"/api/v1/rate-cards/{rule.card_id}/rules",
        data=_valid_payload(
            date_from=rule.date_to.isoformat(),
            date_to="2026-10-31",
            min_party=rule.min_party,
            max_party=rule.max_party,
        ),
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "date_from" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_adjacent_rule_succeeds(api_client: APIClient, rule: RateRule) -> None:
    """date_from = stored date_to + 1 day does not overlap an inclusive range."""
    response = api_client.post(
        f"/api/v1/rate-cards/{rule.card_id}/rules",
        data=_valid_payload(
            date_from="2026-09-01",  # rule fixture ends 2026-08-31
            date_to="2026-10-31",
            min_party=rule.min_party,
            max_party=rule.max_party,
        ),
        format="json",
    )
    assert response.status_code == 201, response.content


@pytest.mark.django_db
def test_patch_rule_does_not_overlap_against_itself(api_client: APIClient, rule: RateRule) -> None:
    response = api_client.patch(
        f"/api/v1/rules/{rule.pk}",
        data={"nightly": "300.00"},
        format="json",
    )
    assert response.status_code == 200, response.content
