from __future__ import annotations

from zoneinfo import ZoneInfo, available_timezones

import pytest
from django.core.exceptions import ValidationError

from properties.timezones import (
    COUNTRY_TIMEZONES,
    representative_timezone,
    validate_iana_timezone,
)


class TestValidateIanaTimezone:
    def test_accepts_real_zone(self) -> None:
        validate_iana_timezone("Europe/Paris")  # no raise

    def test_accepts_utc(self) -> None:
        validate_iana_timezone("UTC")  # no raise

    @pytest.mark.parametrize("bogus", ["Mars/Phobos", "", "Europe/Atlantis"])
    def test_rejects_bogus(self, bogus: str) -> None:
        with pytest.raises(ValidationError):
            validate_iana_timezone(bogus)


class TestRepresentativeTimezone:
    def test_known_country(self) -> None:
        assert representative_timezone("IT") == "Europe/Rome"

    def test_unknown_country_falls_back_to_utc(self) -> None:
        assert representative_timezone("ZZ") == "UTC"

    def test_every_mapped_zone_is_a_real_iana_name(self) -> None:
        names = available_timezones()
        for iso2, tz in COUNTRY_TIMEZONES.items():
            assert tz in names, f"{iso2} -> {tz} is not a valid IANA name"


class TestTzdataAvailable:
    """Regression guard: fails loudly if the `tzdata` package is ever dropped.

    The deploy image (python:3.13-slim) ships no system zoneinfo, so these
    resolve only because `tzdata` is an explicit dependency (FG-008).
    """

    def test_europe_paris_present(self) -> None:
        assert "Europe/Paris" in available_timezones()

    def test_zoneinfo_resolves(self) -> None:
        assert ZoneInfo("Europe/Paris") is not None
