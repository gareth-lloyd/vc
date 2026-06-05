"""IANA timezone helpers for properties.

A property's timezone is a *geographic fact of the place* (it follows the
country), not an operator-chosen policy — hence it lives on `PropertyLocation`
beside `country`, and is derived from the country at creation time.

`available_timezones()` resolves against the `tzdata` package (an explicit
unconditional dependency), so this works on the `python:3.13-slim` deploy image
which ships no system zoneinfo. See FG-008.
"""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import available_timezones

from django.core.exceptions import ValidationError

# The portfolio's actual countries -> a representative IANA zone. Multi-zone
# countries map to the zone the portfolio occupies; a future property in a
# different zone of the same country is a genuine ops outlier corrected in the
# admin. Keep in sync with the inlined copy in the backfill migration.
COUNTRY_TIMEZONES: dict[str, str] = {
    "GB": "Europe/London",
    "FR": "Europe/Paris",
    "ES": "Europe/Madrid",
    "IT": "Europe/Rome",
    "GR": "Europe/Athens",
    "PT": "Europe/Lisbon",
    "CH": "Europe/Zurich",
    "BB": "America/Barbados",
    "BL": "America/St_Barthelemy",
    "ID": "Asia/Makassar",
    "TH": "Asia/Bangkok",
    "MX": "America/Cancun",
}


def representative_timezone(country_iso2: str) -> str:
    """Best-guess IANA zone for a country; UTC when unknown.

    UTC is the honest fallback for an unmapped country — wrong-but-flagged
    (ops corrects it) rather than silently asserting a plausible-looking zone.
    """
    return COUNTRY_TIMEZONES.get(country_iso2, "UTC")


@lru_cache(maxsize=1)
def _iana_names() -> frozenset[str]:
    return frozenset(available_timezones())


def validate_iana_timezone(value: str) -> None:
    if value not in _iana_names():
        raise ValidationError(
            "%(value)s is not a valid IANA timezone name",
            params={"value": value},
        )
