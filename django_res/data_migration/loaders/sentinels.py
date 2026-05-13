"""Sentinel "unknown" rows used as fallbacks when a legacy FK can't be
resolved.

Pattern mirrors the in-line "Uncategorised" PropertyCategory fallback in
`loaders/properties.py`. Stable `legacy_id='__unknown__'` keeps the rows
idempotent across re-runs.
"""

from __future__ import annotations

from properties.models.geo import Country, Region
from properties.models.property import PropertyGroup

_UNKNOWN = "__unknown__"


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


def unknown_group() -> PropertyGroup:
    group, _ = PropertyGroup.objects.get_or_create(
        legacy_id=_UNKNOWN,
        defaults={
            "name": "Unknown",
            "description": "Sentinel group for legacy properties with no resolvable group.",
            "is_active": False,
        },
    )
    return group
