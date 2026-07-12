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

from datetime import date
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
        data={"name": "Inverted", "date_from": "2099-06-08", "date_to": "2099-06-01"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "date_to" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_single_day_period_succeeds(api_client: APIClient, plan: RatePlan) -> None:
    """GAP-056: inclusive dates — date_from == date_to is a valid one-day period."""
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        data={"name": "One day", "date_from": "2099-06-01", "date_to": "2099-06-01"},
        format="json",
    )
    assert response.status_code == 201, response.content


@pytest.mark.django_db
def test_patch_period_dates_validates_against_stored_counterpart(
    api_client: APIClient, future_period: RatePeriod
) -> None:
    """Moving date_from past the stored date_to must be rejected."""
    assert future_period.date_to.isoformat() == "2099-08-31"
    response = api_client.patch(
        f"/api/v1/periods/{future_period.pk}",
        data={"date_from": "2099-09-15"},
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


# --- Q-018: reduction fields ---------------------------------------------------


@pytest.mark.django_db
def test_patch_percent_reduction_succeeds_and_exposes_effective(
    api_client: APIClient, rule: RateBand
) -> None:
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={
            "reduction_percent": "20.00",
            "reduced_at": "2026-05-01",
            "reduction_reason": "Slow June",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["reduction_percent"] == "20.00"
    assert payload["effective_nightly"] == "160.00"
    assert payload["effective_weekly"] is None
    rule.refresh_from_db()
    assert rule.reduction_percent == Decimal("20.00")
    assert rule.reduction_reason == "Slow June"


@pytest.mark.django_db
def test_patch_fixed_pair_reduction_succeeds(api_client: APIClient, rule: RateBand) -> None:
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={
            "weekly": "1300.00",
            "reduced_nightly": "150.00",
            "reduced_weekly": "1000.00",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["effective_nightly"] == "150.00"
    assert payload["effective_weekly"] == "1000.00"


@pytest.mark.django_db
def test_reduction_percent_and_fixed_are_mutually_exclusive(
    api_client: APIClient, rule: RateBand
) -> None:
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"reduction_percent": "20.00", "reduced_nightly": "150.00"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "reduction_percent" in response.json()["field_errors"]


@pytest.mark.django_db
@pytest.mark.parametrize("pct", ["0.00", "100.00", "-5.00"])
def test_reduction_percent_must_be_between_0_and_100_exclusive(
    api_client: APIClient, rule: RateBand, pct: str
) -> None:
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"reduction_percent": pct},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "reduction_percent" in response.json()["field_errors"]


@pytest.mark.django_db
@pytest.mark.parametrize("amount", ["200.00", "250.00", "0.00", "-10.00"])
def test_fixed_reduction_must_be_between_zero_and_base(
    api_client: APIClient, rule: RateBand, amount: str
) -> None:
    """Base nightly is 200.00 — the reduced amount must sit strictly inside (0, base)."""
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"reduced_nightly": amount},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "reduced_nightly" in response.json()["field_errors"]


@pytest.mark.django_db
def test_fixed_reduction_without_matching_base_rejected(
    api_client: APIClient, rule: RateBand
) -> None:
    """`rule` has no weekly price, so a reduced weekly has nothing to reduce."""
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"reduced_weekly": "100.00"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "reduced_weekly" in response.json()["field_errors"]


@pytest.mark.django_db
def test_poa_band_cannot_carry_reduction(api_client: APIClient, rule: RateBand) -> None:
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"is_poa": True, "nightly": None, "weekly": None, "reduction_percent": "20.00"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "is_poa" in response.json()["field_errors"]


@pytest.mark.django_db
def test_fixed_reduction_must_cover_every_base_price(api_client: APIClient, rule: RateBand) -> None:
    """Decision 6b: quoting prefers nightly, so a weekly-only fixed reduction on a
    two-price band would be a silent no-op — force the pair to be complete."""
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"weekly": "1300.00", "reduced_weekly": "1000.00"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "reduced_nightly" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_lowering_base_below_stored_reduction_is_friendly_400(
    api_client: APIClient, rule: RateBand
) -> None:
    """Review M2: the MatrixCell inline editor PATCHes only `nightly` — the clash
    with a stored reduced amount must key its error on the field being edited."""
    rule.reduced_nightly = Decimal("150.00")
    rule.save()
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"nightly": "100.00"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "nightly" in response.json()["field_errors"]


@pytest.mark.django_db
def test_removing_last_reduction_value_clears_metadata(
    api_client: APIClient, rule: RateBand
) -> None:
    rule.reduction_percent = Decimal("20.00")
    rule.reduced_at = date(2026, 5, 1)
    rule.reduction_reason = "Slow June"
    rule.save()
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"reduction_percent": None},
        format="json",
    )
    assert response.status_code == 200, response.content
    rule.refresh_from_db()
    assert rule.reduction_percent is None
    assert rule.reduced_at is None
    assert rule.reduction_reason == ""


@pytest.mark.django_db
def test_effective_prices_are_read_only(api_client: APIClient, rule: RateBand) -> None:
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"effective_nightly": "1.00"},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["effective_nightly"] == "200.00"
    rule.refresh_from_db()
    assert rule.nightly == Decimal("200.00")


@pytest.mark.django_db
def test_fixed_onto_stored_percent_keys_error_on_sent_field(
    api_client: APIClient, rule: RateBand
) -> None:
    """M2 routing: the 400 must land on a field the client actually sent."""
    rule.reduction_percent = Decimal("20.00")
    rule.save()
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"reduced_nightly": "150.00"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "reduced_nightly" in response.json()["field_errors"]


@pytest.mark.django_db
def test_clearing_base_with_stored_reduction_keys_error_on_base_field(
    api_client: APIClient, rule: RateBand
) -> None:
    """Moving a band to weekly-only pricing while a stored nightly reduction
    exists must complain on `nightly` — the field the editor rendered."""
    rule.reduced_nightly = Decimal("150.00")
    rule.save()
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"nightly": None, "weekly": "1300.00"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "nightly" in response.json()["field_errors"]


@pytest.mark.django_db
def test_metadata_without_reduction_rejected(api_client: APIClient, rule: RateBand) -> None:
    """Explicitly-sent metadata with no reduction is a 400, not a silent drop."""
    response = api_client.patch(
        f"/api/v1/bands/{rule.pk}",
        data={"reduction_reason": "Owner agreed cut"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "reduction_reason" in response.json()["field_errors"]
