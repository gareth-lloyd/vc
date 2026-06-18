"""API tests for /properties/{id}/settings — timezone surfacing (FG-008).

Timezone physically lives on `PropertyLocation` (a geographic fact of the
place) but is surfaced through the settings endpoint so ops edit it beside the
check-in/out times it contextualises.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.models import (
    Country,
    GroupSettings,
    Property,
    PropertyLocation,
    PropertySettings,
)


@pytest.fixture
def location(property_: Property, country: Country) -> PropertyLocation:
    return PropertyLocation.objects.create(
        property=property_,
        country=country,
        timezone="Europe/London",
    )


@pytest.fixture
def gbp(db: None) -> Currency:
    return Currency.objects.create(code="GBP", name="Pound sterling", symbol="£")


@pytest.fixture
def eur(db: None) -> Currency:
    return Currency.objects.create(code="EUR", name="Euro", symbol="€")


@pytest.mark.django_db
def test_get_settings_returns_location_timezone(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["timezone"] == "Europe/London"


@pytest.mark.django_db
def test_get_settings_timezone_null_when_no_location(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["timezone"] is None


@pytest.mark.django_db
def test_patch_settings_ignores_timezone_write(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
) -> None:
    # `timezone` is read-only on settings — the location endpoint is the sole
    # writer. A timezone in the settings PATCH is silently ignored, not applied.
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"timezone": "Europe/Rome"},
        format="json",
    )
    assert response.status_code == 200, response.content
    location.refresh_from_db()
    assert location.timezone == "Europe/London"
    assert response.json()["timezone"] == "Europe/London"


@pytest.mark.django_db
def test_get_settings_query_count_pins_location_join(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
) -> None:
    """The settings GET joins `property.location` up front, so reading the
    timezone adds no per-request SELECT. Pin the count so a dropped
    `select_related` (the N+1 regression) is caught."""
    api_client.force_login(staff)
    # Warm the request once so the `get_or_create` of PropertySettings is an
    # existing-row SELECT (not an INSERT) on the measured call.
    api_client.get(f"/api/v1/properties/{property_.pk}/settings")

    with assert_max_queries(6):
        response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["timezone"] == "Europe/London"


@pytest.mark.django_db
def test_patch_settings_other_field_leaves_timezone(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
) -> None:
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"check_in_time": "16:00"},
        format="json",
    )
    assert response.status_code == 200, response.content
    location.refresh_from_db()
    assert location.timezone == "Europe/London"


# --- currency_code (GAP-026): group-resolved effective currency as a string ---


@pytest.mark.django_db
def test_currency_code_uses_property_level_currency(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency, eur: Currency
) -> None:
    """A property-level currency wins over the group fallback."""
    PropertySettings.objects.update_or_create(property=property_, defaults={"currency": gbp})
    # A post_save signal auto-creates the group's settings row; update it.
    GroupSettings.objects.update_or_create(group=property_.group, defaults={"currency": eur})

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["currency_code"] == "GBP"


@pytest.mark.django_db
def test_currency_code_falls_back_to_group(
    api_client: APIClient, staff: User, property_: Property, eur: Currency
) -> None:
    """A null property-level currency inherits the group's."""
    PropertySettings.objects.update_or_create(property=property_, defaults={"currency": None})
    GroupSettings.objects.update_or_create(group=property_.group, defaults={"currency": eur})

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["currency_code"] == "EUR"


@pytest.mark.django_db
def test_currency_code_null_when_neither_set(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """No property or group currency resolves to null, not a blank string."""
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["currency_code"] is None


@pytest.mark.django_db
def test_currency_code_null_when_missing_group_settings(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """When the group has no settings row, `effective()` raises
    `ObjectDoesNotExist`; the except-branch falls back to the (null)
    property-level value → null, not a 500. Delete the signal-created row to
    exercise this defensive path."""
    PropertySettings.objects.update_or_create(property=property_, defaults={"currency": None})
    GroupSettings.objects.filter(group=property_.group).delete()

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["currency_code"] is None


@pytest.mark.django_db
def test_get_settings_query_count_includes_currency_chain(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
    eur: Currency,
) -> None:
    """The group-fallback currency leg is select_related, so resolving
    `currency_code` from the group adds no per-request SELECT. Pin the count so
    a dropped `select_related` (the N+1 regression) is caught."""
    GroupSettings.objects.update_or_create(group=property_.group, defaults={"currency": eur})
    api_client.force_login(staff)
    # Warm the request so the PropertySettings `get_or_create` is a SELECT.
    api_client.get(f"/api/v1/properties/{property_.pk}/settings")

    with assert_max_queries(6):
        response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["currency_code"] == "EUR"


@pytest.mark.django_db
def test_get_settings_query_count_pins_property_currency_join(
    api_client: APIClient,
    staff: User,
    property_: Property,
    location: PropertyLocation,
    gbp: Currency,
) -> None:
    """The property-level currency leg resolves via `select_related("currency")`,
    adding no per-request SELECT. The group-fallback test pins the *other* leg;
    this one guards the common (property sets its own currency) path so dropping
    either `select_related` is caught."""
    PropertySettings.objects.update_or_create(property=property_, defaults={"currency": gbp})
    api_client.force_login(staff)
    # Warm the request so the PropertySettings `get_or_create` is a SELECT.
    api_client.get(f"/api/v1/properties/{property_.pk}/settings")

    with assert_max_queries(6):
        response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["currency_code"] == "GBP"
