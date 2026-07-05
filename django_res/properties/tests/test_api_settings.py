"""API tests for /properties/{id}/settings — timezone surfacing (FG-008).

Timezone physically lives on `PropertyLocation` (a geographic fact of the
place) but is surfaced through the settings endpoint so ops edit it beside the
check-in/out times it contextualises.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.tests import assert_max_queries
from pricing.models import Currency
from properties.enums import CommissionCalcType, PriceBasis
from properties.models import (
    Country,
    GroupFinance,
    GroupSettings,
    Property,
    PropertyFinance,
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


# --- currency_code (GAP-026): the property's currency as a string code ------


@pytest.mark.django_db
def test_currency_code_uses_property_level_currency(
    api_client: APIClient, staff: User, property_: Property, gbp: Currency, eur: Currency
) -> None:
    """The property's own currency is projected as its string code."""
    PropertySettings.objects.update_or_create(property=property_, defaults={"currency": gbp})
    # Group-level currency must be IGNORED (GAP-070: no runtime inheritance).
    GroupSettings.objects.update_or_create(group=property_.group, defaults={"currency": eur})

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["currency_code"] == "GBP"


@pytest.mark.django_db
def test_currency_code_null_when_property_currency_unset(
    api_client: APIClient, staff: User, property_: Property, eur: Currency
) -> None:
    """A null property-level currency stays null — group values are never
    consulted (GAP-070: currency has no runtime fallback)."""
    PropertySettings.objects.update_or_create(property=property_, defaults={"currency": None})
    GroupSettings.objects.update_or_create(group=property_.group, defaults={"currency": eur})

    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["currency_code"] is None


@pytest.mark.django_db
def test_currency_code_null_when_neither_set(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """No property currency resolves to null, not a blank string."""
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
    """The currency leg is select_related, so resolving `currency_code` adds
    no per-request SELECT. Pin the count so a dropped `select_related` (the
    N+1 regression) is caught."""
    PropertySettings.objects.update_or_create(property=property_, defaults={"currency": eur})
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


# --- calendar_url (GAP-034): owner's online (non-iCal) calendar webpage ---


@pytest.mark.django_db
def test_get_settings_calendar_url_null_when_unset(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """`calendar_url` is exposed and defaults to null when never set."""
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["calendar_url"] is None


@pytest.mark.django_db
def test_patch_settings_sets_calendar_url(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """PATCHing a URL persists it and GET echoes it back."""
    api_client.force_login(staff)
    url = "https://owner.example.com/calendar"
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"calendar_url": url},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["calendar_url"] == url

    get_response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert get_response.json()["calendar_url"] == url


@pytest.mark.django_db
def test_patch_settings_null_clears_calendar_url(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """Clearing the field is the real FE path: SettingsTab's `blankToNull` turns
    an emptied input into `null` on submit, so `null` must clear (not 400)."""
    PropertySettings.objects.update_or_create(
        property=property_, defaults={"calendar_url": "https://owner.example.com/calendar"}
    )
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"calendar_url": None},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["calendar_url"] is None


@pytest.mark.django_db
def test_patch_settings_null_clears_min_nights_rental_note(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """`min_nights_rental_note` is inheritable, so `null` (SettingsTab's
    `blankToNull` clearing an empty note on submit) must clear it, not 400.
    Regression: an emptied note used to 400 the whole Operational form, and the
    generic banner made it look like the calendar URL edit had failed."""
    PropertySettings.objects.update_or_create(
        property=property_, defaults={"min_nights_rental_note": "No New Year weeks"}
    )
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"min_nights_rental_note": None},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["min_nights_rental_note"] is None


@pytest.mark.django_db
def test_patch_settings_invalid_calendar_url_returns_400(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """The Django `URLField` validator is stricter than the FE's; a malformed
    URL is rejected server-side."""
    api_client.force_login(staff)
    response = api_client.patch(
        f"/api/v1/properties/{property_.pk}/settings",
        data={"calendar_url": "not a url"},
        format="json",
    )
    assert response.status_code == 400, response.content
    assert "calendar_url" in response.json()["field_errors"]


# --- GAP-035: net↔gross rate-entry derivation context -----------------------
#
# The rate-band form derives the net/gross counterpart on display (never
# persisting it — that would double-count against the BUG-009 engine carve-out).
# The math needs three inputs the settings endpoint surfaces read-only beside
# `currency_code`: the property's *default* basis
# (`prices_entered_as_effective`), the effective commission, and the effective
# tax policy.


@pytest.mark.django_db
def test_prices_entered_as_effective_uses_property_level(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertySettings.objects.update_or_create(
        property=property_, defaults={"prices_entered_as": PriceBasis.NET}
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["prices_entered_as_effective"] == "net"


@pytest.mark.django_db
def test_prices_entered_as_effective_defaults_to_gross(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """Property null → GROSS (the hardcoded default basis)."""
    PropertySettings.objects.update_or_create(
        property=property_, defaults={"prices_entered_as": None}
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["prices_entered_as_effective"] == "gross"


@pytest.mark.django_db
def test_rate_entry_commission_reflects_property_level(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """A property-level commission override wins over the group floor."""
    PropertyFinance.objects.update_or_create(
        property=property_,
        defaults={
            "commission_calculation_type": CommissionCalcType.PERCENT,
            "commission_amount": Decimal("15.00"),
        },
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["commission"] == {"calculation_type": "percent", "amount": "15.00"}


@pytest.mark.django_db
def test_rate_entry_commission_null_columns_resolve_to_policy_floor(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """Null commission columns resolve to the policy floor (percent / 0) —
    group values are never consulted (GAP-070)."""
    GroupFinance.objects.update_or_create(
        group=property_.group,
        defaults={
            "commission_calculation_type": CommissionCalcType.FIXED,
            "commission_amount": Decimal("500.00"),
        },
    )
    PropertyFinance.objects.update_or_create(
        property=property_,
        defaults={"commission_calculation_type": None, "commission_amount": None},
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["commission"] == {"calculation_type": "percent", "amount": "0"}


@pytest.mark.django_db
def test_rate_entry_commission_null_without_property_finance_row(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    """No PropertyFinance row at all → null commission/tax ("not configured"),
    not a 500. Real properties always have a row post-GAP-070 (creation
    snapshot + freeze migration); this is the factory/legacy edge."""
    assert not PropertyFinance.objects.filter(property=property_).exists()
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["commission"] is None
    assert response.json()["tax"] is None


@pytest.mark.django_db
def test_rate_entry_tax_reflects_effective_policy(
    api_client: APIClient, staff: User, property_: Property
) -> None:
    PropertyFinance.objects.update_or_create(
        property=property_,
        defaults={"tax_is_exempt": False, "tax_percentage": Decimal("13.00")},
    )
    api_client.force_login(staff)
    response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["tax"] == {"percentage": "13.00", "is_exempt": False}


@pytest.mark.django_db
def test_get_settings_query_count_includes_finance_chain(
    api_client: APIClient,
    staff: User,
    property_: Property,
) -> None:
    """The effective commission/tax legs (`finance`, `group__finance`) are
    select_related, so resolving the derivation context adds no per-request
    SELECT. Pin the count so a dropped join (the N+1 regression) is caught."""
    PropertyFinance.objects.update_or_create(
        property=property_,
        defaults={
            "commission_calculation_type": CommissionCalcType.PERCENT,
            "commission_amount": Decimal("18.00"),
        },
    )
    api_client.force_login(staff)
    # Warm the request so the PropertySettings `get_or_create` is a SELECT.
    api_client.get(f"/api/v1/properties/{property_.pk}/settings")

    with assert_max_queries(6):
        response = api_client.get(f"/api/v1/properties/{property_.pk}/settings")
    assert response.status_code == 200, response.content
    assert response.json()["commission"]["amount"] == "18.00"
