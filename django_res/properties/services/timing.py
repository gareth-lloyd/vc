"""Wall-clock check-in / check-out as tz-aware datetimes.

The one tested seam that combines a booking date with the property's effective
check-in / check-out time *and* its location timezone into a real instant.
Downstream consumers (reminder emails, ICS feeds, pricing changeover) call this
rather than treating the naive `TimeField` as if it were UTC.

Tolerant by design, mirroring `reservations.services.availability`
`_resolve_changeover_times`: a property with no settings, no effective time, or
no location row simply has no computable instant — returns ``None``, never
raises. Stays in the `properties` layer (takes a `date`; no `reservations`
import), so the import-linter spine is undisturbed.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ObjectDoesNotExist


def _local_datetime(property: Any, on_date: date, time_field: str) -> datetime | None:
    """Effective wall-clock time on ``on_date`` as an aware datetime, or None.

    Callers iterating many bookings should ``select_related`` the property's
    ``settings`` and ``location`` — this reads both.
    """
    try:
        wall_clock: time | None = getattr(property.settings, time_field)
        tz = property.location.timezone
    except (ObjectDoesNotExist, AttributeError):
        return None
    if wall_clock is None:
        return None
    try:
        zone = ZoneInfo(tz)
    except ZoneInfoNotFoundError:
        # The field validator runs on full_clean(), not on .save()/.update(), so
        # a non-IANA string can still reach the column via a raw write. Stay
        # tolerant rather than crash a downstream worker.
        return None
    return datetime.combine(on_date, wall_clock, tzinfo=zone)


def local_check_in_datetime(property: Any, on_date: date) -> datetime | None:
    return _local_datetime(property, on_date, "check_in_time")


def local_check_out_datetime(property: Any, on_date: date) -> datetime | None:
    return _local_datetime(property, on_date, "check_out_time")
