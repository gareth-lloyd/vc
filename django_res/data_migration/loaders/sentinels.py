"""Sentinel "unknown" rows used as fallbacks when a legacy FK can't be
resolved.

Pattern mirrors the in-line "Uncategorised" PropertyCategory fallback in
`loaders/properties.py`. Stable `legacy_id='__unknown__'` keeps the rows
idempotent across re-runs.
"""

from __future__ import annotations

from accounts.enums import PersonKind, PersonStatus
from accounts.models import Person
from properties.models.geo import Country, Region

_UNKNOWN = "__unknown__"

# Canonical `legacy_id` prefix for the customer Persons `ClientLoader` writes
# (`client-{VillaClientDetailsId}`). Single source of truth so the loader write,
# the `person_for_client` read, and the `reconcile_legacy` count slices can never
# drift.
CLIENT_LEGACY_PREFIX = "client-"

# Fixed legacy_id for the `unknown_client` sentinel Person. Carries the
# `client-` prefix so it sorts with the customer rows, but reconcile_legacy
# excludes it from BOTH Person count slices (owner/agent AND client) so the
# documented VillaClientDetails gap stays stable whether or not it's minted.
UNKNOWN_CLIENT_LEGACY_ID = f"{CLIENT_LEGACY_PREFIX}{_UNKNOWN}"


def unknown_country() -> Country:
    country, _ = Country.objects.get_or_create(
        iso2="XX",
        defaults={
            "name": "Unknown",
            "iso3": "XXX",
            "is_active": False,
            "legacy_id": _UNKNOWN,
        },
    )
    return country


def unknown_region(country: Country) -> Region:
    region, _ = Region.objects.get_or_create(
        country=country,
        slug=f"unknown-{country.iso2.lower()}",
        defaults={
            "name": "Unknown",
            "is_active": False,
            "legacy_id": _UNKNOWN,
        },
    )
    return region


def unknown_client() -> Person:
    """Sentinel CUSTOMER Person for a legacy client `ClientLoader` skipped.

    GAP-045 D5-3: downstream loaders (booking / quotation / preference) resolve
    their customer via `person_for_client`. The one documented no-name
    VillaClientDetails row is skipped by `ClientLoader`, so a booking/quotation
    referencing it would otherwise have no `client-{id}` Person to point at. Per
    the sentinel-fallback convention we fall back to this stable row rather than
    dropping the downstream object (silent data loss). Idempotent on its fixed
    `legacy_id`.
    """
    person, _ = Person.objects.get_or_create(
        legacy_id=UNKNOWN_CLIENT_LEGACY_ID,
        defaults={
            "first_name": "Unknown",
            "last_name": "Client",
            "status": PersonStatus.INACTIVE.value,
            "kind": PersonKind.CUSTOMER.value,
        },
    )
    return person
