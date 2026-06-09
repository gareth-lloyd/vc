"""Provisioning for a property's `PropertyLocation`.

A `Property` born outside the data migration / seed factory (e.g. via the
create API) has no `PropertyLocation` row. `ensure_property_location` lazily
heals that: it is the single source of truth for "a property's default
location", replacing the hand-rolled copies in the loader, factory, and the
settings serializer's timezone write.

The default `country` comes from the property's non-nullable `region` FK (so it
is always derivable) and the `timezone` from `representative_timezone`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from properties.models import PropertyLocation
from properties.timezones import representative_timezone

if TYPE_CHECKING:
    from properties.models import Property


def location_defaults(property_: Property) -> dict[str, Any]:
    """Default field values for a property's location, derived from its region."""
    country = property_.region.country
    return {"country": country, "timezone": representative_timezone(country.iso2)}


def ensure_property_location(property_: Property) -> PropertyLocation:
    """Return the property's location, creating a default one if absent.

    Idempotent: `property` is the OneToOne primary key, so a concurrent
    double-create raises `IntegrityError`, which `get_or_create` resolves by
    re-fetching. An existing row is returned untouched.
    """
    location, _ = PropertyLocation.objects.get_or_create(
        property=property_,
        defaults=location_defaults(property_),
    )
    return location
