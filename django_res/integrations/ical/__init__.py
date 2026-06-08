"""Pure iCal parsing for the calendar-feed poller (GAP-011).

This subpackage holds NO domain imports — it sits at the `integrations` layer
and only knows how to turn `.ics` bytes into normalized busy date-ranges plus
the per-source quirk profiles. The reconciliation that turns those ranges into
owner-availability blocks lives in `reservations` (which may import down into
here), keeping the spine layering intact.
"""

from __future__ import annotations

from integrations.ical.parser import (
    BusyInterval,
    coalesce_intervals,
    normalize_feed_url,
    parse_busy_intervals,
)
from integrations.ical.profiles import (
    CalendarFeedPlatform,
    IcalSourceProfile,
    detect_platform,
    resolve_profile,
)

__all__ = [
    "BusyInterval",
    "CalendarFeedPlatform",
    "IcalSourceProfile",
    "coalesce_intervals",
    "detect_platform",
    "normalize_feed_url",
    "parse_busy_intervals",
    "resolve_profile",
]
