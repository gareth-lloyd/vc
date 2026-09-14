"""API tests for /rate-plans, /rate-periods, /bands CRUD (GAP-056)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import cast

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from pricing.factories import RatePlanFactory
from pricing.models import Currency, RateBand, RatePeriod, RatePlan
from properties.factories import PropertyFactory
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
    """GAP-110: a plan is a date-less regime bucket — no envelope in or out. A
    client still sending the pre-GAP-110 date pair (the SPA, until U5b) is
    not rejected: the fields are unknown to the serializer and dropped."""
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans",
        data={
            "name": "Winter 2027",
            "currency": gbp.pk,
            "is_active": True,
            "effective_from": "2027-01-01",
            "effective_to": "2027-03-31",
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert RatePlan.objects.filter(name="Winter 2027").exists()
    payload = response.json()
    assert "effective_from" not in payload
    assert "effective_to" not in payload


@pytest.mark.django_db
def test_create_rate_period(api_client: APIClient, staff: User, plan: RatePlan) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        data={
            "name": "Peak",
            "date_from": "2099-07-01",
            "date_to": "2099-08-31",
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
        data={"date_from": "2099-07-01", "date_to": "2099-08-31"},
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
        data={"name": blank, "date_from": "2099-07-01", "date_to": "2099-08-31"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "name" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_period_cannot_clear_name(
    api_client: APIClient, staff: User, future_period: RatePeriod
) -> None:
    """GAP-059: an existing name cannot be cleared back to blank."""
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/periods/{future_period.pk}",
        data={"name": ""},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "name" in response.json()["field_errors"]


@pytest.mark.django_db
def test_create_rate_rule_under_period(
    api_client: APIClient, staff: User, future_period: RatePeriod
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/periods/{future_period.pk}/bands",
        data={"min_party": 1, "max_party": 6, "nightly": "180.00"},
        format="json",
    )
    assert response.status_code == 201, response.content
    created = RateBand.objects.get(period=future_period, nightly=Decimal("180.00"))
    # The band hangs off the period and inherits its dates (GAP-056 — no own
    # date columns).
    assert created.period_id == future_period.pk


@pytest.mark.django_db
def test_get_rate_rule_detail(api_client: APIClient, staff: User, rule: RateBand) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/bands/{rule.pk}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == rule.pk
    assert body["period"] == rule.period_id


@pytest.mark.django_db
def test_delete_rate_period(api_client: APIClient, staff: User, future_period: RatePeriod) -> None:
    api_client.force_login(staff)
    response = api_client.delete(f"/api/v1/periods/{future_period.pk}")
    assert response.status_code == 204
    assert not RatePeriod.objects.filter(pk=future_period.pk).exists()


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
    api_client: APIClient, staff: User, plan: RatePlan, future_period: RatePeriod
) -> None:
    """Periods on one plan must be date-disjoint (Unit 9 EXCLUDE surfaced as 400)."""
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        # Shares 08-31 with `future_period`. Named: a missing name would
        # 400 at field level (GAP-059) before the overlap check runs.
        data={"name": "Autumn", "date_from": "2099-08-31", "date_to": "2099-09-30"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "date_from" in response.json()["field_errors"]


@pytest.mark.django_db
def test_patch_period_dates(api_client: APIClient, staff: User, future_period: RatePeriod) -> None:
    """Moving a period's dates moves the effective dates of its bands, which
    inherit them (GAP-056 — bands have no own date columns)."""
    band = RateBand.objects.create(
        period=future_period,
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/periods/{future_period.pk}",
        data={"date_from": "2099-06-15", "date_to": "2099-09-15"},
        format="json",
    )
    assert response.status_code == 200, response.content
    future_period.refresh_from_db()
    assert future_period.date_from == date(2099, 6, 15)
    assert future_period.date_to == date(2099, 9, 15)
    # The band still hangs off the moved period — it inherits the new span.
    assert band.period_id == future_period.pk


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


# --- Flat-vs-occupancy pricing mode -----------------------------------------


@pytest.mark.django_db
def test_create_rate_plan_defaults_to_flat(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency
) -> None:
    """A new plan is flat (party size ignored) unless opted into occupancy."""
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans",
        data={"name": "New", "currency": gbp.pk},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["prices_by_occupancy"] is False


@pytest.mark.django_db
def test_rate_plan_detail_exposes_pricing_mode(
    api_client: APIClient, staff: User, plan: RatePlan
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/rate-plans/{plan.pk}")
    assert response.status_code == 200, response.content
    assert response.json()["prices_by_occupancy"] is True


@pytest.mark.django_db
def test_switch_plan_to_flat_rejected_while_period_has_multiple_bands(
    api_client: APIClient, staff: User, plan: RatePlan, period: RatePeriod
) -> None:
    """Occupancy → flat is blocked until each period is reduced to one band."""
    for lo, hi in ((1, 8), (9, 12)):
        RateBand.objects.create(period=period, min_party=lo, max_party=hi, nightly=Decimal("200"))
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{plan.pk}",
        data={"prices_by_occupancy": False},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "prices_by_occupancy" in response.json()["field_errors"]
    plan.refresh_from_db()
    assert plan.prices_by_occupancy is True


@pytest.mark.django_db
def test_switch_plan_to_flat_allowed_with_single_band_per_period(
    api_client: APIClient, staff: User, plan: RatePlan, period: RatePeriod
) -> None:
    RateBand.objects.create(period=period, min_party=1, max_party=8, nightly=Decimal("200"))
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{plan.pk}",
        data={"prices_by_occupancy": False},
        format="json",
    )
    assert response.status_code == 200, response.content
    plan.refresh_from_db()
    assert plan.prices_by_occupancy is False


@pytest.mark.django_db
def test_switch_flat_plan_to_occupancy_always_allowed(
    api_client: APIClient, staff: User, flat_plan: RatePlan, flat_period: RatePeriod
) -> None:
    RateBand.objects.create(period=flat_period, min_party=1, max_party=8, nightly=Decimal("200"))
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{flat_plan.pk}",
        data={"prices_by_occupancy": True},
        format="json",
    )
    assert response.status_code == 200, response.content
    flat_plan.refresh_from_db()
    assert flat_plan.prices_by_occupancy is True


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
    assert rule.period is not None
    # GAP-110: the carried periods land on the regime plan itself — the
    # response is that plan (with its new periods inlined), not a new row.
    assert payload["id"] == rule.period.plan_id
    assert RatePlan.objects.filter(property=property_).count() == 1
    carried = RatePeriod.objects.filter(plan_id=payload["id"], date_from__year=2028)
    assert carried.exists()
    assert {p["date_from"][:4] for p in payload["periods"]} == {"2026", "2028"}
    # GAP-059: every carried period arrives named (exact naming rules are the
    # service's contract — see test_carryover).
    assert all(p.name for p in carried)


@pytest.mark.django_db
def test_carry_forward_into_a_year_owned_by_withdrawn_rows_returns_409(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    rule: RateBand,
) -> None:
    """GAP-110: a period a retired sibling plan still owns in the target year
    sits in the regime-wide EXCLUDE; the carry is refused as a 409
    `regime_conflict` with guidance (service contract — see test_carryover)
    rather than silently landing nothing."""
    owner = cast(
        RatePlan,
        RatePlanFactory(property=property_, currency=gbp, is_active=False),
    )
    RatePeriod.objects.create(
        plan=owner, name="Owned", date_from=date(2028, 6, 15), date_to=date(2028, 8, 31)
    )
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans:carry-forward",
        {"currency": gbp.code, "target_year": 2028},
        format="json",
    )
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "regime_conflict"
    assert "Owned" in response.json()["detail"]
    assert not RatePeriod.objects.filter(plan=rule.period.plan, date_from__year=2028).exists()


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


@pytest.mark.django_db
def test_create_period_overlapping_another_plans_period_rejected(
    api_client: APIClient,
    staff: User,
    plan: RatePlan,
    sibling_plan: RatePlan,
    future_period: RatePeriod,
) -> None:
    """GAP-110: the no-overlap rule is per (property, currency) regime, not
    per plan — the pre-check names the other plan so the operator knows where
    the clash lives."""
    other = sibling_plan
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/rate-plans/{other.pk}/rate-periods",
        data={"name": "Clash", "date_from": "2099-07-01", "date_to": "2099-07-31"},
        format="json",
    )
    assert response.status_code == 400, response.content
    [message] = response.json()["field_errors"]["date_from"]
    assert plan.name in message
    assert not other.periods.exists()


@pytest.mark.django_db
def test_create_period_raced_past_precheck_maps_to_409(
    api_client: APIClient,
    staff: User,
    plan: RatePlan,
    sibling_plan: RatePlan,
    future_period: RatePeriod,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A racing writer that slips past the serializer pre-check trips the
    EXCLUDE; the view maps that `IntegrityError` to a 409 `regime_conflict`
    rather than a 500. Simulated by silencing the pre-check."""
    from pricing.serializers.rate import RatePeriodSerializer

    monkeypatch.setattr(RatePeriodSerializer, "validate", lambda self, attrs: attrs)
    other = sibling_plan
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/rate-plans/{other.pk}/rate-periods",
        data={"name": "Clash", "date_from": "2099-07-01", "date_to": "2099-07-31"},
        format="json",
    )
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "regime_conflict"
    assert not other.periods.exists()


@pytest.mark.django_db
def test_patch_period_dates_onto_another_plans_period_rejected(
    api_client: APIClient,
    staff: User,
    plan: RatePlan,
    sibling_plan: RatePlan,
    future_period: RatePeriod,
) -> None:
    other = sibling_plan
    mine = RatePeriod.objects.create(
        plan=other, name="Sept", date_from=date(2099, 9, 1), date_to=date(2099, 9, 30)
    )
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/periods/{mine.pk}", data={"date_from": "2099-08-15"}, format="json"
    )
    assert response.status_code == 400, response.content
    assert plan.name in response.json()["field_errors"]["date_from"][0]


@pytest.mark.django_db
def test_patch_plan_currency_rejected_once_periods_exist(
    api_client: APIClient, staff: User, plan: RatePlan, period: RatePeriod, usd: Currency
) -> None:
    """GAP-110: periods carry a stamped copy of the plan's currency (the regime
    partition key), so a plan with periods keeps its currency for life."""
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{plan.pk}", data={"currency": usd.pk}, format="json"
    )
    assert response.status_code == 400, response.content
    assert "currency" in response.json()["field_errors"]
    plan.refresh_from_db()
    assert plan.currency_id != usd.pk


@pytest.mark.django_db
def test_patch_plan_property_is_read_only(
    api_client: APIClient, staff: User, plan: RatePlan, period: RatePeriod
) -> None:
    """`property` comes from the URL on create and never moves — a body value
    is ignored (DRF read-only), so the stamped regime key can't drift."""
    other = cast(Property, PropertyFactory())
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{plan.pk}", data={"property": other.pk}, format="json"
    )
    assert response.status_code == 200, response.content
    plan.refresh_from_db()
    assert plan.property_id != other.pk


@pytest.mark.django_db
def test_patch_plan_currency_allowed_while_periodless(
    api_client: APIClient, staff: User, plan: RatePlan, usd: Currency
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{plan.pk}", data={"currency": usd.pk}, format="json"
    )
    assert response.status_code == 200, response.content
    plan.refresh_from_db()
    assert plan.currency_id == usd.pk


@pytest.mark.django_db
def test_patch_plan_same_currency_with_periods_is_fine(
    api_client: APIClient, staff: User, plan: RatePlan, period: RatePeriod
) -> None:
    """Re-sending the current currency (a full PUT-style body) is not a change."""
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{plan.pk}",
        data={"currency": plan.currency_id, "name": "Renamed"},
        format="json",
    )
    assert response.status_code == 200, response.content


# --- One active plan per regime (GAP-110 U4) --------------------------------


@pytest.mark.django_db
def test_create_plan_into_an_occupied_regime_rejected_with_guidance(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans",
        data={"name": "Second GBP", "currency": gbp.pk},
        format="json",
    )
    assert response.status_code == 400, response.content
    [message] = response.json()["field_errors"]["non_field_errors"]
    assert "already has an active GBP gross plan" in message
    assert "carry forward" in message
    assert RatePlan.objects.filter(property=property_).count() == 1


@pytest.mark.django_db
def test_create_plan_in_a_free_regime_is_fine(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans",
        data={
            "name": "Net GBP",
            "currency": gbp.pk,
            "price_basis": "net",
        },
        format="json",
    )
    assert response.status_code == 201, response.content


@pytest.mark.django_db
def test_reactivating_a_plan_into_an_occupied_regime_rejected(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    retired = cast(RatePlan, RatePlanFactory(property=property_, currency=gbp, is_active=False))
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{retired.pk}", data={"is_active": True}, format="json"
    )
    assert response.status_code == 400, response.content
    assert (
        "already has an active GBP gross plan"
        in response.json()["field_errors"]["non_field_errors"][0]
    )
    retired.refresh_from_db()
    assert retired.is_active is False


@pytest.mark.django_db
def test_switching_basis_onto_an_occupied_regime_rejected(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    net = cast(RatePlan, RatePlanFactory(property=property_, currency=gbp, price_basis="net"))
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{net.pk}", data={"price_basis": "gross"}, format="json"
    )
    assert response.status_code == 400, response.content
    assert (
        "already has an active GBP gross plan"
        in response.json()["field_errors"]["non_field_errors"][0]
    )


@pytest.mark.django_db
def test_patching_the_occupying_plan_itself_is_fine(
    api_client: APIClient, staff: User, plan: RatePlan
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{plan.pk}", data={"name": "Renamed", "is_active": True}, format="json"
    )
    assert response.status_code == 200, response.content


@pytest.mark.django_db
def test_create_plan_raced_past_precheck_maps_to_409(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    plan: RatePlan,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pricing.serializers.rate import RatePlanSerializer

    monkeypatch.setattr(RatePlanSerializer, "validate", lambda self, attrs: attrs)
    api_client.force_login(staff)
    response = api_client.post(
        f"/api/v1/properties/{property_.pk}/rate-plans",
        data={"name": "Second GBP", "currency": gbp.pk},
        format="json",
    )
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "regime_conflict"
    assert RatePlan.objects.filter(property=property_).count() == 1


@pytest.mark.django_db
def test_reactivate_plan_raced_past_precheck_maps_to_409(
    api_client: APIClient,
    staff: User,
    property_: Property,
    gbp: Currency,
    plan: RatePlan,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The PATCH route to the constraint (reactivating a retired plan) is
    guarded like the POST route."""
    from pricing.serializers.rate import RatePlanSerializer

    monkeypatch.setattr(RatePlanSerializer, "validate", lambda self, attrs: attrs)
    retired = cast(RatePlan, RatePlanFactory(property=property_, currency=gbp, is_active=False))
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/rate-plans/{retired.pk}", data={"is_active": True}, format="json"
    )
    assert response.status_code == 409, response.content
    assert response.json()["code"] == "regime_conflict"
    retired.refresh_from_db()
    assert retired.is_active is False
