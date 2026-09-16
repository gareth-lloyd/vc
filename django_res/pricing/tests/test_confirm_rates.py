"""GAP-114: staff confirm indicative (carried, owner-unconfirmed) rates.

`POST /rate-plans/{id}:confirm-rates` clears `RateBand.is_indicative` on the
plan's non-historical periods (optionally only those overlapping a date range)
and `PATCH /bands/{id}` can flip the flag one band at a time. Neither touches a
period that has already elapsed (decision 10), and confirming enqueues no
pricing-summary rebuild (the summary never reads the flag).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.models import AuditLog
from pricing.factories import RatePlanFactory
from pricing.models import RateBand, RatePeriod, RatePlan
from pricing.services.carryover import RateCarryoverService


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="confirm-rates@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def viewer(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="confirm-rates-viewer@example.com",
        password="x",
        role=StaffRole.VIEWER,
    )


@pytest.fixture
def api_client(staff: User) -> APIClient:
    client = APIClient()
    client.force_login(staff)
    return client


def _band(period: RatePeriod, *, indicative: bool = True, min_party: int = 1) -> RateBand:
    return RateBand.objects.create(
        period=period,
        min_party=min_party,
        max_party=min_party + 3,
        nightly=Decimal("200.00"),
        is_indicative=indicative,
    )


def _confirm(client: APIClient, plan: RatePlan, body: dict[str, Any] | None = None) -> Any:
    return client.post(f"/api/v1/rate-plans/{plan.pk}:confirm-rates", body or {}, format="json")


# --- POST :confirm-rates ----------------------------------------------------


@pytest.mark.django_db
def test_confirm_without_a_range_clears_every_non_historical_band(
    api_client: APIClient, plan: RatePlan, period: RatePeriod, future_period: RatePeriod
) -> None:
    current = _band(period)
    later = _band(future_period)
    already = _band(future_period, indicative=False, min_party=5)

    response = _confirm(api_client, plan)

    assert response.status_code == 200, response.content
    assert response.json() == {"confirmed": 2}
    assert not RateBand.objects.filter(
        pk__in=[current.pk, later.pk, already.pk], is_indicative=True
    ).exists()


@pytest.mark.django_db
def test_confirm_with_a_range_only_touches_overlapping_periods(
    api_client: APIClient, plan: RatePlan, period: RatePeriod, future_period: RatePeriod
) -> None:
    """The range selects whole periods: one overlapping it is confirmed even
    where it extends past the range; a disjoint period is untouched."""
    current = _band(period)  # 2026-06-01..08-31
    later = _band(future_period)  # 2099

    response = _confirm(api_client, plan, {"date_from": "2026-08-20", "date_to": "2026-12-31"})

    assert response.status_code == 200, response.content
    assert response.json() == {"confirmed": 1}
    current.refresh_from_db()
    later.refresh_from_db()
    assert current.is_indicative is False
    assert later.is_indicative is True


@pytest.mark.django_db
def test_confirm_skips_historical_periods(
    api_client: APIClient, plan: RatePlan, period: RatePeriod, past_period: RatePeriod
) -> None:
    current = _band(period)
    old = _band(past_period)

    response = _confirm(api_client, plan)

    assert response.json() == {"confirmed": 1}
    current.refresh_from_db()
    old.refresh_from_db()
    assert current.is_indicative is False
    assert old.is_indicative is True


@pytest.mark.django_db
def test_confirm_leaves_other_plans_alone(
    api_client: APIClient, plan: RatePlan, period: RatePeriod
) -> None:
    other_plan = cast(RatePlan, RatePlanFactory())
    other_period = RatePeriod.objects.create(
        plan=other_plan, name="Other", date_from=date(2026, 6, 1), date_to=date(2026, 8, 31)
    )
    mine = _band(period)
    theirs = _band(other_period)

    _confirm(api_client, plan)

    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert mine.is_indicative is False
    assert theirs.is_indicative is True


@pytest.mark.django_db
def test_confirm_writes_one_audit_diff_per_band(
    api_client: APIClient, staff: User, plan: RatePlan, period: RatePeriod
) -> None:
    """Who confirmed, and when, is the audit trail's job (decision 1)."""
    bands = [_band(period, min_party=1), _band(period, min_party=5)]

    _confirm(api_client, plan)

    ct = ContentType.objects.get_for_model(RateBand)
    for band in bands:
        rows = AuditLog.objects.filter(content_type=ct, object_id=str(band.pk))
        flag_rows = [r for r in rows if "is_indicative" in r.field_diffs]
        assert [r.field_diffs["is_indicative"] for r in flag_rows] == [[True, False]]
        assert flag_rows[0].actor_id == staff.pk


@pytest.mark.django_db
def test_confirm_enqueues_no_summary_rebuild(
    api_client: APIClient,
    plan: RatePlan,
    period: RatePeriod,
    django_capture_on_commit_callbacks: Any,
) -> None:
    _band(period)
    with (
        patch("pricing.signals.rebuild_summary_task.delay") as delay,
        django_capture_on_commit_callbacks(execute=True) as callbacks,
    ):
        response = _confirm(api_client, plan)
    assert response.status_code == 200, response.content
    assert response.json() == {"confirmed": 1}  # saved AND not enqueued
    assert callbacks == []
    delay.assert_not_called()


@pytest.mark.django_db
def test_confirm_requires_the_reservations_writer_role(viewer: User, plan: RatePlan) -> None:
    client = APIClient()
    client.force_login(viewer)
    response = _confirm(client, plan)
    assert response.status_code == 403


@pytest.mark.django_db
def test_confirm_unknown_plan_is_404(api_client: APIClient) -> None:
    response = api_client.post("/api/v1/rate-plans/999999:confirm-rates", {}, format="json")
    assert response.status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "body",
    [
        {"date_from": "nope", "date_to": "2026-12-31"},
        {"date_from": "2026-12-31", "date_to": "2026-06-01"},
        {"date_from": "2026-06-01"},
        {"date_to": "2026-12-31"},
    ],
    ids=["unparseable", "inverted", "from-only", "to-only"],
)
def test_confirm_rejects_a_bad_range(
    api_client: APIClient, plan: RatePlan, period: RatePeriod, body: dict[str, Any]
) -> None:
    band = _band(period)
    response = _confirm(api_client, plan, body)
    assert response.status_code == 400, response.content
    band.refresh_from_db()
    assert band.is_indicative is True


@pytest.mark.django_db
def test_service_refuses_a_half_specified_window(plan: RatePlan, period: RatePeriod) -> None:
    """A non-HTTP caller passing one bound must not silently confirm the plan."""
    band = _band(period)
    with pytest.raises(ValueError, match="both date_from and date_to"):
        RateCarryoverService.confirm(plan, date_from=date(2027, 1, 1))
    band.refresh_from_db()
    assert band.is_indicative is True


# --- PATCH /bands/{id} ------------------------------------------------------


@pytest.mark.django_db
def test_band_serializer_exposes_a_writable_is_indicative(
    api_client: APIClient, period: RatePeriod
) -> None:
    band = _band(period)

    response = api_client.patch(f"/api/v1/bands/{band.pk}", {"is_indicative": False}, format="json")

    assert response.status_code == 200, response.content
    assert response.json()["is_indicative"] is False
    band.refresh_from_db()
    assert band.is_indicative is False


@pytest.mark.django_db
def test_patch_is_indicative_on_a_historical_period_is_rejected(
    api_client: APIClient, past_period: RatePeriod
) -> None:
    band = _band(past_period)

    response = api_client.patch(f"/api/v1/bands/{band.pk}", {"is_indicative": False}, format="json")

    assert response.status_code == 400, response.content
    band.refresh_from_db()
    assert band.is_indicative is True
