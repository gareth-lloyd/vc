from __future__ import annotations

from datetime import date, time
from typing import cast
from zoneinfo import ZoneInfo

import pytest

from properties.factories import PropertyFactory
from properties.models import Property
from properties.services.timing import (
    local_check_in_datetime,
    local_check_out_datetime,
)

pytestmark = pytest.mark.django_db

ON_DATE = date(2026, 7, 15)


def _property_with(check_in: time | None = None, timezone: str = "UTC") -> Property:
    prop = cast(Property, PropertyFactory())
    prop.settings.check_in_time = check_in
    prop.settings.save()
    prop.location.timezone = timezone
    prop.location.save()
    return prop


class TestLocalCheckInDatetime:
    def test_combines_date_time_and_zone(self) -> None:
        prop = _property_with(check_in=time(16, 0), timezone="America/New_York")
        dt = local_check_in_datetime(prop, ON_DATE)
        assert dt is not None
        assert dt.date() == ON_DATE
        assert dt.timetz() == time(16, 0, tzinfo=ZoneInfo("America/New_York"))
        # 15 July is EDT (UTC-4).
        offset = dt.utcoffset()
        assert offset is not None
        assert offset.total_seconds() == -4 * 3600

    def test_same_wall_clock_two_zones_differ_in_utc(self) -> None:
        ny = _property_with(check_in=time(16, 0), timezone="America/New_York")
        rome = _property_with(check_in=time(16, 0), timezone="Europe/Rome")
        ny_dt = local_check_in_datetime(ny, ON_DATE)
        rome_dt = local_check_in_datetime(rome, ON_DATE)
        assert ny_dt is not None and rome_dt is not None
        # Same wall-clock 16:00, but different real instants — the FG-008 footgun.
        assert ny_dt.astimezone(ZoneInfo("UTC")) != rome_dt.astimezone(ZoneInfo("UTC"))

    def test_none_when_check_in_time_unset(self) -> None:
        prop = _property_with(check_in=None, timezone="Europe/Rome")
        assert local_check_in_datetime(prop, ON_DATE) is None

    def test_none_when_location_absent(self) -> None:
        prop = cast(Property, PropertyFactory())
        prop.settings.check_in_time = time(16, 0)
        prop.settings.save()
        prop.location.delete()
        prop.refresh_from_db()
        assert local_check_in_datetime(prop, ON_DATE) is None

    def test_none_when_stored_timezone_invalid(self) -> None:
        # The field validator runs on full_clean(), not on .save()/.update(), so
        # a bad value can reach the column via a raw write. The seam must stay
        # tolerant (return None) rather than raise ZoneInfoNotFoundError.
        prop = _property_with(check_in=time(16, 0), timezone="Europe/Rome")
        prop.location.timezone = "Europe/Atlantis"
        prop.location.save()  # no full_clean → bypasses the validator
        assert local_check_in_datetime(prop, ON_DATE) is None


class TestLocalCheckOutDatetime:
    def test_combines_check_out_time(self) -> None:
        prop = cast(Property, PropertyFactory())
        prop.settings.check_out_time = time(10, 0)
        prop.settings.save()
        prop.location.timezone = "Europe/Rome"
        prop.location.save()
        dt = local_check_out_datetime(prop, ON_DATE)
        assert dt is not None
        assert dt.timetz() == time(10, 0, tzinfo=ZoneInfo("Europe/Rome"))
