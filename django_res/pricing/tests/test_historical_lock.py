"""Historical rate periods are read-only (locked against edits and deletion).

A ``RatePeriod`` whose ``date_to`` is before today is "historical": a frozen
record of what was charged. The serializers/views reject any edit to it or its
bands, and reject deleting either — the workbench hides these rows by default
and disables their controls when shown, and this is the server-side backstop.

Creating a past-dated period through the API is *also* blocked — a period born
historical would be locked on arrival (no bands, unremovable). Only current or
upcoming periods can be created here (loaders backfill via the ORM, which
bypasses the serializer). Dates here are deliberately far in the past (2019) /
future (2999) so the suite stays clock-independent.
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
        email="historical-lock@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.fixture
def api_client(staff: User) -> APIClient:
    client = APIClient()
    client.force_login(staff)
    return client


@pytest.fixture
def past_period(plan: RatePlan) -> RatePeriod:
    """A period whose window fully elapsed (date_to before today)."""
    return RatePeriod.objects.create(
        plan=plan,
        name="Summer 2019",
        date_from=date(2019, 6, 1),
        date_to=date(2019, 8, 31),
    )


@pytest.fixture
def future_period(plan: RatePlan) -> RatePeriod:
    """A period comfortably in the future (never historical)."""
    return RatePeriod.objects.create(
        plan=plan,
        name="Summer 2999",
        date_from=date(2999, 6, 1),
        date_to=date(2999, 8, 31),
    )


# --- Period edits -----------------------------------------------------------


@pytest.mark.django_db
def test_patch_historical_period_rejected(api_client: APIClient, past_period: RatePeriod) -> None:
    response = api_client.patch(
        f"/api/v1/periods/{past_period.pk}",
        data={"name": "Renamed"},
        format="json",
    )
    assert response.status_code == 400, response.content
    # Object-level validate() keys the lock message under non_field_errors.
    assert "ended" in str(response.json()["field_errors"])
    past_period.refresh_from_db()
    assert past_period.name == "Summer 2019"


@pytest.mark.django_db
def test_delete_historical_period_rejected(api_client: APIClient, past_period: RatePeriod) -> None:
    response = api_client.delete(f"/api/v1/periods/{past_period.pk}")
    assert response.status_code == 400, response.content
    assert RatePeriod.objects.filter(pk=past_period.pk).exists()


@pytest.mark.django_db
def test_patch_future_period_allowed(api_client: APIClient, future_period: RatePeriod) -> None:
    response = api_client.patch(
        f"/api/v1/periods/{future_period.pk}",
        data={"name": "Renamed"},
        format="json",
    )
    assert response.status_code == 200, response.content
    future_period.refresh_from_db()
    assert future_period.name == "Renamed"


@pytest.mark.django_db
def test_delete_future_period_allowed(api_client: APIClient, future_period: RatePeriod) -> None:
    response = api_client.delete(f"/api/v1/periods/{future_period.pk}")
    assert response.status_code == 204, response.content
    assert not RatePeriod.objects.filter(pk=future_period.pk).exists()


@pytest.mark.django_db
def test_create_past_dated_period_rejected(api_client: APIClient, plan: RatePlan) -> None:
    """A period that has already ended can't be created — it would be born locked."""
    response = api_client.post(
        f"/api/v1/rate-plans/{plan.pk}/rate-periods",
        data={"name": "Backfill 2018", "date_from": "2018-01-01", "date_to": "2018-12-31"},
        format="json",
    )
    assert response.status_code == 400, response.content
    # Keyed under `date_to`, so it lands in field_errors (not the detail string).
    assert "ended" in str(response.json()["field_errors"])
    assert not RatePeriod.objects.filter(plan=plan, name="Backfill 2018").exists()


# --- Band edits on a historical period --------------------------------------


@pytest.mark.django_db
def test_create_band_on_historical_period_rejected(
    api_client: APIClient, past_period: RatePeriod
) -> None:
    response = api_client.post(
        f"/api/v1/periods/{past_period.pk}/bands",
        data={"min_party": 1, "max_party": 8, "nightly": "150.00"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "ended" in str(response.json()["field_errors"])
    assert not RateBand.objects.filter(period=past_period).exists()


@pytest.mark.django_db
def test_patch_band_on_historical_period_rejected(
    api_client: APIClient, past_period: RatePeriod
) -> None:
    band = RateBand.objects.create(
        period=past_period, min_party=1, max_party=8, nightly=Decimal("200.00")
    )
    response = api_client.patch(
        f"/api/v1/bands/{band.pk}",
        data={"nightly": "999.00"},
        format="json",
    )
    assert response.status_code == 400, response.content
    band.refresh_from_db()
    assert band.nightly == Decimal("200.00")


@pytest.mark.django_db
def test_delete_band_on_historical_period_rejected(
    api_client: APIClient, past_period: RatePeriod
) -> None:
    band = RateBand.objects.create(
        period=past_period, min_party=1, max_party=8, nightly=Decimal("200.00")
    )
    response = api_client.delete(f"/api/v1/bands/{band.pk}")
    assert response.status_code == 400, response.content
    assert RateBand.objects.filter(pk=band.pk).exists()


@pytest.mark.django_db
def test_band_ops_on_future_period_allowed(
    api_client: APIClient, future_period: RatePeriod
) -> None:
    create = api_client.post(
        f"/api/v1/periods/{future_period.pk}/bands",
        data={"min_party": 1, "max_party": 8, "nightly": "150.00"},
        format="json",
    )
    assert create.status_code == 201, create.content
    band_id = create.json()["id"]

    patch = api_client.patch(f"/api/v1/bands/{band_id}", data={"nightly": "175.00"}, format="json")
    assert patch.status_code == 200, patch.content

    delete = api_client.delete(f"/api/v1/bands/{band_id}")
    assert delete.status_code == 204, delete.content
