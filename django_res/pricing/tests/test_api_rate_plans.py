"""API tests for /rate-plans, /rate-periods, /bands CRUD + duplicate action (GAP-056)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.models import Currency, RateBand, RatePeriod, RatePlan
from properties.models import Property, PropertyCapacity


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="rate_plans@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_list_rate_plans_for_property(
    api_client: APIClient,
    staff: User,
    property_: Property,
    plan: RatePlan,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/rate-plans")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] >= 1
    row = next(r for r in payload["results"] if r["id"] == plan.pk)
    assert row["currency"] == plan.currency_id
    assert row["currency_code"] == plan.currency.code


@pytest.mark.django_db
def test_rate_plan_detail_exposes_currency_code(
    api_client: APIClient,
    staff: User,
    plan: RatePlan,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/rate-plans/{plan.pk}")
    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["currency"] == plan.currency_id
    assert payload["currency_code"] == plan.currency.code


@pytest.mark.django_db
def test_create_rate_plan(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans",
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
def test_rate_plan_duplicate_copies_periods_and_rules(
    api_client: APIClient,
    staff: User,
    plan: RatePlan,
    period: RatePeriod,
    rule: RateBand,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(f"/api/v1/rate-plans/{plan.pk}:duplicate")
    assert response.status_code == 201, response.content
    payload = response.json()
    cloned = RatePlan.objects.get(pk=payload["id"])
    assert cloned.periods.count() == 1
    first_period = cloned.periods.first()
    assert first_period is not None
    assert first_period.bands.count() == 1
    # GAP-056: the clone's bands must hang off periods on the CLONE's plan, not
    # the source plan's.
    cloned_rule = first_period.bands.get()
    assert cloned_rule.period_id == first_period.pk
    assert first_period.plan_id == cloned.pk


@pytest.mark.django_db
def test_create_rate_period(api_client: APIClient, staff: User, plan: RatePlan) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        data={
            "name": "Peak",
            "date_from": "2026-07-01",
            "date_to": "2026-08-31",
            "min_nights": 7,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert RatePeriod.objects.filter(plan=plan, name="Peak").exists()


@pytest.mark.django_db
def test_create_period_requires_name(api_client: APIClient, staff: User, plan: RatePlan) -> None:
    """GAP-059: the operator label is compulsory at the write surface."""
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        data={"date_from": "2026-07-01", "date_to": "2026-08-31"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "name" in response.json()["field_errors"]


@pytest.mark.django_db
@pytest.mark.parametrize("blank", ["", "   "])
def test_create_period_rejects_blank_name(
    api_client: APIClient, staff: User, plan: RatePlan, blank: str
) -> None:
    """GAP-059: blank and whitespace-only names are rejected (DRF trims)."""
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        data={"name": blank, "date_from": "2026-07-01", "date_to": "2026-08-31"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "name" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_period_cannot_clear_name(
    api_client: APIClient, staff: User, period: RatePeriod
) -> None:
    """GAP-059: an existing name cannot be cleared back to blank."""
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/periods/{period.pk}",
        data={"name": ""},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "name" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_rate_rule_under_period(
    api_client: APIClient, staff: User, period: RatePeriod
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/periods/{period.pk}/bands",
        data={"min_party": 1, "max_party": 6, "nightly": "180.00"},
        format="json",
    )
    assert response.status_code == 201, response.content
    created = RateBand.objects.get(period=period, nightly=Decimal("180.00"))
    # The band hangs off the period and inherits its dates (GAP-056 — no own
    # date columns).
    assert created.period_id == period.pk


@pytest.mark.django_db
def test_get_rate_rule_detail(api_client: APIClient, staff: User, rule: RateBand) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bands/{rule.pk}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == rule.pk
    assert body["period"] == rule.period_id


@pytest.mark.django_db
def test_delete_rate_period(api_client: APIClient, staff: User, period: RatePeriod) -> None:
    api_client.force_login(staff)
    response = api_client.delete(f"/api/v1/periods/{period.pk}")
    assert response.status_code == 204
    assert not RatePeriod.objects.filter(pk=period.pk).exists()


@pytest.mark.django_db
def test_rate_plan_detail_inlines_periods_with_rules(
    api_client: APIClient,
    staff: User,
    plan: RatePlan,
    period: RatePeriod,
    rule: RateBand,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/rate-plans/{plan.pk}")
    assert response.status_code == 200, response.content
    payload = response.json()
    assert "periods" in payload
    assert len(payload["periods"]) == 1
    assert len(payload["periods"][0]["bands"]) == 1
    assert payload["periods"][0]["coverage_gaps"] == []


@pytest.mark.django_db
def test_create_period_rejects_overlapping_dates(
    api_client: APIClient, staff: User, plan: RatePlan, period: RatePeriod
) -> None:
    """Periods on one plan must be date-disjoint (Unit 9 EXCLUDE surfaced as 400)."""
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        # Shares 08-31 with the fixture period. Named: a missing name would
        # 400 at field level (GAP-059) before the overlap check runs.
        data={"name": "Autumn", "date_from": "2026-08-31", "date_to": "2026-09-30"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "date_from" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_period_dates(api_client: APIClient, staff: User, period: RatePeriod) -> None:
    """Moving a period's dates moves the effective dates of its bands, which
    inherit them (GAP-056 — bands have no own date columns)."""
    band = RateBand.objects.create(
        period=period,
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/periods/{period.pk}",
        data={"date_from": "2026-06-15", "date_to": "2026-09-15"},
        format="json",
    )
    assert response.status_code == 200, response.content
    period.refresh_from_db()
    assert period.date_from == date(2026, 6, 15)
    assert period.date_to == date(2026, 9, 15)
    # The band still hangs off the moved period — it inherits the new span.
    assert band.period_id == period.pk


@pytest.mark.django_db
def test_activate_period_with_party_gap_rejected(
    api_client: APIClient,
    staff: User,
    property_: Property,
    period: RatePeriod,
) -> None:
    """An active period must price every party 1..max_occupancy (POA is a band)."""
    PropertyCapacity.objects.create(property=property_, guests=8)
    # One band covering only 1..4 leaves 5..8 uncovered.
    RateBand.objects.create(
        period=period,
        min_party=1,
        max_party=4,
        nightly=Decimal("200.00"),
    )
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/periods/{period.pk}",
        data={"is_active": True},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "is_active" in response.json()["field_errors"]


@pytest.mark.django_db
def test_period_coverage_gaps_reports_uncovered_ranges(
    api_client: APIClient,
    staff: User,
    property_: Property,
    period: RatePeriod,
) -> None:
    PropertyCapacity.objects.create(property=property_, guests=8)
    RateBand.objects.create(
        period=period,
        min_party=1,
        max_party=4,
        nightly=Decimal("200.00"),
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/periods/{period.pk}")
    assert response.status_code == 200, response.content
    assert response.json()["coverage_gaps"] == [[5, 8]]


# Touch a couple of variables to silence "unused" complaints from the linter.
_ = (date, Decimal)


# --- Carry-forward (promote projection to editable rows) --------------------


@pytest.mark.django_db
def test_carry_forward_creates_editable_plan_for_future_year(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateBand,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans:carry-forward",
        {"currency": gbp.code, "target_year": 2028},
        format="json",
    )
    assert response.status_code == 201, response.content
    payload = response.json()
    assert payload["effective_from"] == "2028-01-01"
    assert rule.period is not None
    assert payload["id"] != rule.period.plan_id
    # The materialised plan is a real, queryable row distinct from the anchor.
    assert RatePlan.objects.filter(property=property_, effective_from__year=2028).exists()
    # GAP-059: every carried period arrives named (exact naming rules are the
    # service's contract — see test_carryover).
    carried = RatePeriod.objects.filter(plan_id=payload["id"])
    assert carried.exists()
    assert all(p.name for p in carried)


@pytest.mark.django_db
def test_carry_forward_without_anchor_returns_409(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans:carry-forward",
        {"currency": gbp.code, "target_year": 2028},
        format="json",
    )
    assert response.status_code == 409, response.content


@pytest.mark.django_db
def test_carry_forward_requires_currency_and_year(
    api_client: APIClient,
    staff: User,
    property_: Property,
    rule: RateBand,
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans:carry-forward",
        {"target_year": 2028},
        format="json",
    )
    assert response.status_code == 400, response.content


@pytest.mark.django_db
def test_carry_forward_rejects_out_of_range_year(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateBand,
) -> None:
    """Out-of-range years return 400, not an uncaught ValueError (500)."""
    api_client.force_login(staff)
    for bad_year in (0, 99999, -5):
        response = api_client.post(
            f"/api/v1/properties/{property_.pk}/rate-plans:carry-forward",
            {"currency": gbp.code, "target_year": bad_year},
            format="json",
        )
        assert response.status_code == 400, (bad_year, response.content)
