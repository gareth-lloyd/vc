"""Generic iCal parser → busy date-ranges on the half-open ``[date_from, date_to)``.

Off-the-shelf parsing via the ``icalendar`` library, with recurrence expansion via
``recurring-ical-events``; this module only normalizes the output (scheme, all-day
vs timed, DTEND convention) and coalesces overlaps. It holds no domain knowledge —
the caller decides what a busy range *means*, and supplies the window to expand
recurrences over (recurrences are otherwise unbounded).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import recurring_ical_events
from icalendar import Calendar

from integrations.ical.profiles import IcalSourceProfile


@dataclass(frozen=True)
class BusyInterval:
    """One busy event, normalized to a half-open ``[date_from, date_to)`` range."""

    date_from: date
    date_to: date  # exclusive — checkout morning, matching our range model
    uid: str
    summary: str


def normalize_feed_url(url: str) -> str:
    """``webcal://`` is plain ``https://`` with a scheme swap for subscription."""
    if url.startswith("webcal://"):
        return "https://" + url[len("webcal://") :]
    return url


def _as_date(value: date | datetime) -> date:
    """All-day events yield ``date``; timed events yield ``datetime``."""
    if isinstance(value, datetime):
        return value.date()
    return value


def parse_busy_intervals(
    ics_text: str,
    profile: IcalSourceProfile,
    *,
    window_start: date,
    window_end: date,
) -> list[BusyInterval]:
    """Parse ``.ics`` text into busy intervals over ``[window_start, window_end]``.

    Recurring events (``RRULE``/``RDATE``, minus ``EXDATE``) are expanded into
    their individual occurrences across the window; one-off events overlapping the
    window are returned too. Each occurrence is normalized to a half-open
    ``[date_from, date_to)`` range, and CANCELLED (and, per profile, TENTATIVE)
    events are dropped. The window is required because recurrences are otherwise
    unbounded — the caller picks a horizon and re-polls to roll it forward.

    Raises ``ValueError`` on malformed input — a non-calendar body or a malformed
    recurrence rule — so the poller catches it per feed and one bad feed never
    aborts the run. Any other parse/expansion failure is normalized to
    ``ValueError`` to keep that single documented contract.
    """
    try:
        calendar = Calendar.from_ical(ics_text)
        occurrences = recurring_ical_events.of(calendar).between(window_start, window_end)
    except ValueError:
        raise
    except Exception as exc:  # honor the documented ValueError contract
        raise ValueError(f"Unparseable iCal feed: {exc}") from exc

    intervals: list[BusyInterval] = []
    for component in occurrences:
        status = str(component.get("status", "")).upper()
        if status == "CANCELLED":
            continue
        if status == "TENTATIVE" and not profile.tentative_is_busy:
            continue

        dtstart = component.get("dtstart")
        if dtstart is None:
            continue
        start = _as_date(dtstart.dt)

        dtend = component.get("dtend")
        if dtend is not None:
            end = _as_date(dtend.dt)
            if profile.dtend_inclusive:
                end = end + timedelta(days=1)
        else:
            # No DTEND: an all-day event covers a single day; a timed event we
            # also collapse to its start day.
            end = start + timedelta(days=1)

        # Guard against zero/negative-length or same-day timed events: a busy
        # event always occupies at least one night.
        if end <= start:
            end = start + timedelta(days=1)

        intervals.append(
            BusyInterval(
                date_from=start,
                date_to=end,
                uid=str(component.get("uid", "")),
                summary=str(component.get("summary", "")),
            )
        )
    return intervals


def coalesce_intervals(intervals: list[BusyInterval]) -> list[tuple[date, date]]:
    """Merge overlapping or adjacent ``[from, to)`` ranges into disjoint ranges.

    Adjacent ranges (``prev_end == start``) merge too: two back-to-back bookings
    are one continuous unavailable block. Coalescing across *all* of a property's
    feeds is what keeps the poller from inserting two overlapping holds (which
    the ``bookinghold_no_overlap_live`` constraint would reject).
    """
    ordered = sorted((iv.date_from, iv.date_to) for iv in intervals)
    merged: list[tuple[date, date]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            prev_start, prev_end = merged[-1]
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged
