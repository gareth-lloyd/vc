"""Unit tests for the shared location-provisioning helper.

`ensure_property_location` is the single source of truth for "a property's
default location", replacing the hand-rolled copies in the loader, factory, and
settings serializer. Default country comes from the (non-nullable) region FK and
the timezone from `representative_timezone`.
"""

from __future__ import annotations

import pytest

from properties.models import Property, PropertyLocation
from properties.services.location import (
    ensure_property_location,
    location_defaults,
)


@pytest.mark.django_db
def test_location_defaults_derive_from_region_country(property_: Property) -> None:
    defaults = location_defaults(property_)
    assert defaults["country"] == property_.region.country
    # GB region → Europe/London (see COUNTRY_TIMEZONES).
    assert defaults["timezone"] == "Europe/London"


@pytest.mark.django_db
def test_ensure_creates_default_location(property_: Property) -> None:
    assert not PropertyLocation.objects.filter(property=property_).exists()
    location = ensure_property_location(property_)
    assert location.property_id == property_.pk
    assert location.country == property_.region.country
    assert location.timezone == "Europe/London"


@pytest.mark.django_db
def test_ensure_is_idempotent_and_reuses_existing(property_: Property) -> None:
    existing = PropertyLocation.objects.create(
        property=property_,
        country=property_.region.country,
        timezone="Europe/Rome",
    )
    location = ensure_property_location(property_)
    assert location.pk == existing.pk
    # Existing row is not overwritten with the default timezone.
    assert location.timezone == "Europe/Rome"
    assert PropertyLocation.objects.filter(property=property_).count() == 1
