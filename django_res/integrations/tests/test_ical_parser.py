"""Tests for the pure iCal parser + profiles (no DB)."""

from __future__ import annotations

from datetime import date

from integrations.ical import (
    BusyInterval,
    coalesce_intervals,
    normalize_feed_url,
    parse_busy_intervals,
    resolve_profile,
)
from integrations.ical.profiles import CalendarFeedPlatform, IcalSourceProfile, detect_platform

DEFAULT = resolve_profile()


def _ics(*events: str) -> str:
    body = "".join(events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n{body}END:VCALENDAR\r\n"


def _event(
    uid: str,
    dtstart: str,
    dtend: str | None = None,
    *,
    all_day: bool = True,
    status: str | None = None,
    summary: str = "Reserved",
) -> str:
    lines = ["BEGIN:VEVENT", f"UID:{uid}", f"SUMMARY:{summary}"]
    if all_day:
        lines.append(f"DTSTART;VALUE=DATE:{dtstart}")
        if dtend:
            lines.append(f"DTEND;VALUE=DATE:{dtend}")
    else:
        lines.append(f"DTSTART:{dtstart}")
        if dtend:
            lines.append(f"DTEND:{dtend}")
    if status:
        lines.append(f"STATUS:{status}")
    lines.append("END:VEVENT")
    return "\r\n".join(lines) + "\r\n"


def test_normalize_webcal_swaps_scheme() -> None:
    assert normalize_feed_url("webcal://host.test/a.ics") == "https://host.test/a.ics"
    assert normalize_feed_url("https://host.test/a.ics") == "https://host.test/a.ics"


def test_all_day_exclusive_dtend_maps_directly() -> None:
    [interval] = parse_busy_intervals(_ics(_event("a", "20260701", "20260705")), DEFAULT)
    # RFC DTEND = checkout morning (exclusive) → our half-open model directly.
    assert interval.date_from == date(2026, 7, 1)
    assert interval.date_to == date(2026, 7, 5)


def test_inclusive_dtend_profile_adds_a_day() -> None:
    profile = IcalSourceProfile(dtend_inclusive=True)
    [interval] = parse_busy_intervals(_ics(_event("a", "20260701", "20260705")), profile)
    assert interval.date_to == date(2026, 7, 6)


def test_cancelled_event_is_skipped() -> None:
    assert (
        parse_busy_intervals(_ics(_event("a", "20260701", "20260705", status="CANCELLED")), DEFAULT)
        == []
    )


def test_tentative_busy_by_default_but_profile_can_drop() -> None:
    ics = _ics(_event("a", "20260701", "20260705", status="TENTATIVE"))
    assert len(parse_busy_intervals(ics, DEFAULT)) == 1
    assert parse_busy_intervals(ics, IcalSourceProfile(tentative_is_busy=False)) == []


def test_missing_dtend_is_one_night() -> None:
    [interval] = parse_busy_intervals(_ics(_event("a", "20260701")), DEFAULT)
    assert interval.date_from == date(2026, 7, 1)
    assert interval.date_to == date(2026, 7, 2)


def test_timed_event_collapses_to_a_day() -> None:
    ics = _ics(_event("a", "20260701T140000Z", "20260701T170000Z", all_day=False))
    [interval] = parse_busy_intervals(ics, DEFAULT)
    assert interval.date_from == date(2026, 7, 1)
    assert interval.date_to == date(2026, 7, 2)


def test_empty_calendar_yields_no_intervals() -> None:
    assert parse_busy_intervals(_ics(), DEFAULT) == []


def test_coalesce_merges_overlapping_and_adjacent() -> None:
    intervals = [
        BusyInterval(date(2026, 7, 1), date(2026, 7, 5), "a", ""),
        BusyInterval(date(2026, 7, 5), date(2026, 7, 8), "b", ""),  # adjacent → merges
        BusyInterval(date(2026, 7, 4), date(2026, 7, 6), "d", ""),  # overlaps first
        BusyInterval(date(2026, 7, 10), date(2026, 7, 12), "c", ""),  # separate
    ]
    assert coalesce_intervals(intervals) == [
        (date(2026, 7, 1), date(2026, 7, 8)),
        (date(2026, 7, 10), date(2026, 7, 12)),
    ]


def test_detect_platform_from_host() -> None:
    assert (
        detect_platform("https://www.airbnb.com/calendar/ical/1.ics")
        == CalendarFeedPlatform.AIRBNB.value
    )
    assert (
        detect_platform("https://calendar.google.com/ical/x/basic.ics")
        == CalendarFeedPlatform.GOOGLE.value
    )
    assert detect_platform("https://example.test/a.ics") == CalendarFeedPlatform.OTHER.value
