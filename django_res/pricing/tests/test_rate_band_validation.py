"""Serializer-level validation for RatePeriod dates and RateBand bands (GAP-056).

Dates now live on the ``RatePeriod``; the band (``RateBand``) carries only the
party range + price. The serializers pre-validate the DB constraints so the
client gets a 400 with ``field_errors`` instead of a 500 ``IntegrityError``:

* period ``date_from`` on or before ``date_to`` (inclusive; single-day allowed),
* period dates disjoint from sibling periods on the plan,
* band ``min_party`` <= ``max_party``,
* at least one of ``nightly`` / ``weekly`` / ``is_poa``,
* ``is_poa`` excludes ``nightly`` / ``weekly``,
* bands on one period cover disjoint party ranges.

PATCH merges the incoming attrs with the stored instance before checking, so a
partial update can't sneak a stored+incoming combination past a constraint.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.models import RateBand, RatePeriod, RatePlan


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


def _valid_band(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "min_party": 1,
        "max_party": 8,
        "nightly": "150.00",
    }
    payload.update(overrides)
    return payload


# --- Period date validation -------------------------------------------------


@pytest.mark.django_db
def test_create_period_rejects_inverted_date_range(api_client: APIClient, plan: RatePlan) -> None:
    """An inverted span (date_from after date_to) is rejected."""
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        data={"name": "Inverted", "date_from": "2026-06-08", "date_to": "2026-06-01"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "date_to" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_single_day_period_succeeds(api_client: APIClient, plan: RatePlan) -> None:
    """GAP-056: inclusive dates — date_from == date_to is a valid one-day period."""
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        data={"name": "One day", "date_from": "2026-06-01", "date_to": "2026-06-01"},
        format="json",
    )
    assert response.status_code == 201, response.content


@pytest.mark.django_db
def test_patch_period_dates_validates_against_stored_counterpart(
    api_client: APIClient, period: RatePeriod
) -> None:
    """Moving date_from past the stored date_to must be rejected."""
    assert period.date_to.isoformat() == "2026-08-31"
    response = api_client.patch(
        f"/api/v1/periods/{period.pk}",
        data={"date_from": "2026-09-15"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "date_to" in response.json()["field_errors"]


# --- Band party / price validation ------------------------------------------


@pytest.mark.django_db
def test_create_band_rejects_min_party_above_max_party(
    api_client: APIClient, period: RatePeriod
) -> None:
    response = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(min_party=9, max_party=2),
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "max_party" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_band_requires_price_or_poa(api_client: APIClient, period: RatePeriod) -> None:
    response = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(nightly=None),
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "nightly" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_band_rejects_poa_with_price(api_client: APIClient, period: RatePeriod) -> None:
    response = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(is_poa=True),
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "is_poa" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_poa_only_band_succeeds(api_client: APIClient, period: RatePeriod) -> None:
    response = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(nightly=None, is_poa=True),
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["is_poa"] is True


@pytest.mark.django_db
def test_patch_poa_onto_priced_band_rejected_without_clearing_price(
    api_client: APIClient, rule: RateBand
) -> None:
    """Partial update must merge stored attrs: stored nightly + incoming POA clash."""
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"is_poa": True},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "is_poa" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_poa_onto_priced_band_succeeds_when_prices_cleared(
    api_client: APIClient, rule: RateBand
) -> None:
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"is_poa": True, "nightly": None, "weekly": None},
        format="json",
    )
    assert response.status_code == 200, response.content
    rule.refresh_from_db()
    assert rule.is_poa is True
    assert rule.nightly is None


@pytest.mark.django_db
def test_patch_priced_band_price_change_succeeds(api_client: APIClient, rule: RateBand) -> None:
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"nightly": "275.00"},
        format="json",
    )
    assert response.status_code == 200, response.content
    rule.refresh_from_db()
    assert rule.nightly == Decimal("275.00")


@pytest.mark.django_db
def test_create_band_omitting_defaulted_min_party_still_validates(
    api_client: APIClient, period: RatePeriod
) -> None:
    """Omitted min_party falls back to the model default (1), so max_party=0 clashes."""
    payload = _valid_band(max_party=0)
    del payload["min_party"]
    response = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=payload,
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "max_party" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_band_overlapping_party_returns_400(
    api_client: APIClient, period: RatePeriod
) -> None:
    """Two bands sharing a party count in one period overlap → 400, not 500."""
    # Seed an existing band 1..4 through the API so the transitional card is set.
    seed = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(min_party=1, max_party=4),
        format="json",
    )
    assert seed.status_code == 201, seed.content
    response = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(min_party=3, max_party=8),  # overlaps 3..4
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "min_party" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_adjacent_party_band_succeeds(api_client: APIClient, period: RatePeriod) -> None:
    """Disjoint party bands (1..4 then 5..8) on one period both persist."""
    first = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(min_party=1, max_party=4),
        format="json",
    )
    assert first.status_code == 201, first.content
    second = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(min_party=5, max_party=8),
        format="json",
    )
    assert second.status_code == 201, second.content


@pytest.mark.django_db
def test_patch_band_does_not_overlap_against_itself(api_client: APIClient, rule: RateBand) -> None:
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"nightly": "300.00"},
        format="json",
    )
    assert response.status_code == 200, response.content


# --- Flat-plan mode: a single band per period -------------------------------


@pytest.mark.django_db
def test_flat_plan_accepts_first_band(api_client: APIClient, flat_period: RatePeriod) -> None:
    """A flat plan still needs its one price row — the first band is allowed."""
    response = api_client.post(
        f"/api/v1/periods/{flat_period.pk}/bands",
        data=_valid_band(min_party=1, max_party=8),
        format="json",
    )
    assert response.status_code == 201, response.content


@pytest.mark.django_db
def test_flat_plan_rejects_second_band(api_client: APIClient, flat_period: RatePeriod) -> None:
    """Adding a second (occupancy) band to a flat plan's period is rejected."""
    first = api_client.post(
        f"/api/v1/periods/{flat_period.pk}/bands",
        data=_valid_band(min_party=1, max_party=8),
        format="json",
    )
    assert first.status_code == 201, first.content
    response = api_client.post(
        f"/api/v1/periods/{flat_period.pk}/bands",
        data=_valid_band(min_party=9, max_party=12),
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "prices_by_occupancy" in response.json()["field_errors"]


@pytest.mark.django_db
def test_occupancy_plan_accepts_second_band(api_client: APIClient, period: RatePeriod) -> None:
    """The shared `period` hangs off an occupancy plan — second bands are fine."""
    first = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(min_party=1, max_party=8),
        format="json",
    )
    assert first.status_code == 201, first.content
    second = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data=_valid_band(min_party=9, max_party=12),
        format="json",
    )
    assert second.status_code == 201, second.content
