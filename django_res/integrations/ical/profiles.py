"""Per-source iCal quirk profiles.

Every busy event in a feed collapses to one owner-availability block — VC does
not care whether a date is "booked on Airbnb" or "owner blocked", only that it
is not bookable through VC. That semantic collapse lets a single generic parser
serve every source; sources differ only in *data quirks*, captured here as
declarative profiles rather than per-OTA code paths. Add an override when a
source proves it needs one; never branch the parser per villa.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import models


class CalendarFeedPlatform(models.TextChoices):
    """The publishing platform behind a feed — used to resolve its profile.

    Lives in `integrations` (not `properties`) so the spine layering holds:
    `properties.PropertyCalendarFeed` imports this *down*, and the pure parser
    here never imports *up* into a domain app.
    """

    AIRBNB = "airbnb", "Airbnb"
    VRBO = "vrbo", "Vrbo / HomeAway"
    BOOKING_COM = "booking_com", "Booking.com"
    GOOGLE = "google", "Google Calendar"
    OTHER = "other", "Other"


@dataclass(frozen=True)
class IcalSourceProfile:
    """Declarative quirks for one calendar source.

    dtend_inclusive: RFC 5545 all-day events emit ``DTEND`` as the checkout
        *morning* (exclusive), which maps straight onto our half-open
        ``[date_from, date_to)`` range model. A few non-conformant feeds emit
        ``DTEND`` as the last busy *night* (inclusive); set this True so the
        parser adds a day and lands on the same model.
    tentative_is_busy: whether ``STATUS:TENTATIVE`` events block. Default True —
        a tentative hold on another channel is still a reason not to sell.
    """

    dtend_inclusive: bool = False
    tentative_is_busy: bool = True


_DEFAULT = IcalSourceProfile()

# Known platforms. All major OTAs currently emit RFC-compliant exclusive DTEND,
# so they share the default — but each is listed as the explicit override point
# for when a source is discovered to misbehave (e.g. flip dtend_inclusive here).
_PROFILES: dict[str, IcalSourceProfile] = {
    CalendarFeedPlatform.AIRBNB.value: _DEFAULT,
    CalendarFeedPlatform.VRBO.value: _DEFAULT,
    CalendarFeedPlatform.BOOKING_COM.value: _DEFAULT,
    CalendarFeedPlatform.GOOGLE.value: _DEFAULT,
    CalendarFeedPlatform.OTHER.value: _DEFAULT,
}

_HOST_HINTS: tuple[tuple[str, str], ...] = (
    ("airbnb.", CalendarFeedPlatform.AIRBNB.value),
    ("vrbo.", CalendarFeedPlatform.VRBO.value),
    ("homeaway.", CalendarFeedPlatform.VRBO.value),
    ("booking.com", CalendarFeedPlatform.BOOKING_COM.value),
    ("google.com", CalendarFeedPlatform.GOOGLE.value),
)


def detect_platform(url: str) -> str:
    """Best-effort platform tag from a feed URL host (for provenance/labels)."""
    host = url.lower()
    for hint, platform in _HOST_HINTS:
        if hint in host:
            return platform
    return CalendarFeedPlatform.OTHER.value


def resolve_profile(platform: str | None = None, *, url: str | None = None) -> IcalSourceProfile:
    """Resolve the parsing profile, preferring an explicit platform over the URL."""
    if platform and platform in _PROFILES:
        return _PROFILES[platform]
    if url:
        return _PROFILES.get(detect_platform(url), _DEFAULT)
    return _DEFAULT
