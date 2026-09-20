"""Sentinel "unknown" rows used as fallbacks when a legacy FK can't be
resolved.

Stable `legacy_id='__unknown__'` keeps the rows idempotent across re-runs.
"""

from __future__ import annotations

from accounts.constants import (
    CLIENT_LEGACY_PREFIX,
    UNKNOWN_CLIENT_LEGACY_ID,
    UNKNOWN_LEGACY_ID,
)
from accounts.enums import PersonKind, PersonStatus
from accounts.models import Person
from properties.models.geo import Country, Region

# GAP-118: `UNKNOWN_LEGACY_ID`, `CLIENT_LEGACY_PREFIX` and the composed
# `UNKNOWN_CLIENT_LEGACY_ID` now live in `accounts.constants` — the API has to
# recognise the sentinel row (`ContactSerializer.is_unknown_client`) and
# `accounts` cannot import `data_migration`. Re-exported here so every existing
# `from data_migration.loaders.sentinels import …` keeps working and the three
# stay single-source; see that module for what each one is.
__all__ = [
    "CLIENT_LEGACY_PREFIX",
    "ENQUIRY_PERSON_LEGACY_PREFIX",
    "SHEET_LEGACY_PREFIX",
    "UNKNOWN_CLIENT_LEGACY_ID",
    "UNKNOWN_LEGACY_ID",
    "unknown_client",
    "unknown_country",
    "unknown_region",
]

# GAP-089: `legacy_id` prefix shared by every row the spreadsheet importers
# write (`sheet-person-…`, `sheet-stay-…`, `sheet-enquiry-…`). Those rows have
# no res-DB twin, so `reconcile_legacy` excludes the prefix from every count
# that is compared against the legacy dump.
SHEET_LEGACY_PREFIX = "sheet-"

# GAP-118: `legacy_id` prefix for the customer Persons `relink_enquiry_customers
# --mint-unmatched` writes for an enquiry address no loaded Person holds
# (`enquiry-person-<sha1(address)>`, minted by `relink.enquiry_person_legacy_id`).
# Like the `sheet-` rows these have no res-DB twin, so `reconcile_legacy`
# excludes the prefix from the Person count slice it compares against the dump.
ENQUIRY_PERSON_LEGACY_PREFIX = "enquiry-person-"


def unknown_country() -> Country:
    country, _ = Country.objects.get_or_create(
        iso2="XX",
        defaults={
            "name": "Unknown",
            "iso3": "XXX",
            "is_active": False,
            "legacy_id": UNKNOWN_LEGACY_ID,
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
            "legacy_id": UNKNOWN_LEGACY_ID,
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
