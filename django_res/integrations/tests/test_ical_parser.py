"""Tests for the pure iCal parser + profiles (no DB)."""

from __future__ import annotations

from datetime import date

import pytest

from integrations.ical import (
    BusyInterval,
    coalesce_intervals,
    normalize_feed_url,
    parse_busy_intervals,
    resolve_profile,
)
from integrations.ical.profiles import CalendarFeedPlatform, IcalSourceProfile, detect_platform

DEFAULT = resolve_profile()

# Recurrences need a bounded window; the tests use 2026-dated events, so a wide
# window comfortably covers every fixture plus a year of recurrence headroom.
WINDOW_START = date(2026, 1, 1)
WINDOW_END = date(2027, 1, 1)


def _parse(ics: str, profile: IcalSourceProfile = DEFAULT) -> list[BusyInterval]:
    return parse_busy_intervals(ics, profile, window_start=WINDOW_START, window_end=WINDOW_END)


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
    [interval] = _parse(_ics(_event("a", "20260701", "20260705")))
    # RFC DTEND = checkout morning (exclusive) → our half-open model directly.
    assert interval.date_from == date(2026, 7, 1)
    assert interval.date_to == date(2026, 7, 5)


def test_inclusive_dtend_profile_adds_a_day() -> None:
    profile = IcalSourceProfile(dtend_inclusive=True)
    [interval] = _parse(_ics(_event("a", "20260701", "20260705")), profile)
    assert interval.date_to == date(2026, 7, 6)


def test_cancelled_event_is_skipped() -> None:
    assert _parse(_ics(_event("a", "20260701", "20260705", status="CANCELLED"))) == []


def test_tentative_busy_by_default_but_profile_can_drop() -> None:
    ics = _ics(_event("a", "20260701", "20260705", status="TENTATIVE"))
    assert len(_parse(ics)) == 1
    assert _parse(ics, IcalSourceProfile(tentative_is_busy=False)) == []


def test_missing_dtend_is_one_night() -> None:
    [interval] = _parse(_ics(_event("a", "20260701")))
    assert interval.date_from == date(2026, 7, 1)
    assert interval.date_to == date(2026, 7, 2)


def test_timed_event_collapses_to_a_day() -> None:
    ics = _ics(_event("a", "20260701T140000Z", "20260701T170000Z", all_day=False))
    [interval] = _parse(ics)
    assert interval.date_from == date(2026, 7, 1)
    assert interval.date_to == date(2026, 7, 2)


def test_empty_calendar_yields_no_intervals() -> None:
    assert _parse(_ics()) == []


def test_weekly_recurrence_expands_to_each_occurrence() -> None:
    # A single recurring VEVENT (the way Google Calendar emits "every Monday")
    # must expand to one busy interval per occurrence, not just the first.
    rrule_event = (
        "BEGIN:VEVENT\r\nUID:weekly\r\nSUMMARY:Owner block\r\n"
        "DTSTART;VALUE=DATE:20260706\r\nDTEND;VALUE=DATE:20260707\r\n"
        "RRULE:FREQ=WEEKLY;COUNT=4\r\nEND:VEVENT\r\n"
    )
    intervals = _parse(_ics(rrule_event))
    assert sorted(iv.date_from for iv in intervals) == [
        date(2026, 7, 6),
        date(2026, 7, 13),
        date(2026, 7, 20),
        date(2026, 7, 27),
    ]


def test_exdate_drops_a_single_occurrence() -> None:
    rrule_event = (
        "BEGIN:VEVENT\r\nUID:weekly\r\nSUMMARY:Owner block\r\n"
        "DTSTART;VALUE=DATE:20260706\r\nDTEND;VALUE=DATE:20260707\r\n"
        "RRULE:FREQ=WEEKLY;COUNT=4\r\nEXDATE;VALUE=DATE:20260713\r\nEND:VEVENT\r\n"
    )
    intervals = _parse(_ics(rrule_event))
    assert sorted(iv.date_from for iv in intervals) == [
        date(2026, 7, 6),
        date(2026, 7, 20),
        date(2026, 7, 27),
    ]


def test_recurrence_beyond_window_is_not_expanded() -> None:
    # COUNT=200 weekly runs ~4 years out; only occurrences inside the window count.
    rrule_event = (
        "BEGIN:VEVENT\r\nUID:weekly\r\nSUMMARY:Owner block\r\n"
        "DTSTART;VALUE=DATE:20260706\r\nDTEND;VALUE=DATE:20260707\r\n"
        "RRULE:FREQ=WEEKLY;COUNT=200\r\nEND:VEVENT\r\n"
    )
    intervals = parse_busy_intervals(
        _ics(rrule_event),
        DEFAULT,
        window_start=date(2026, 7, 1),
        window_end=date(2026, 8, 1),
    )
    # Mondays in [Jul1, Aug1): 6, 13, 20, 27.
    assert len(intervals) == 4


def test_one_off_event_still_parsed_alongside_recurrence_machinery() -> None:
    # Non-recurring events must keep working after the switch to the expander.
    [interval] = _parse(_ics(_event("solo", "20260701", "20260703")))
    assert interval.date_from == date(2026, 7, 1)
    assert interval.date_to == date(2026, 7, 3)


def test_non_value_error_is_normalized_to_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The poller's per-feed catch is `except (httpx.HTTPError, ValueError)`, so the
    # parser must surface *every* parse/expansion failure as ValueError — even one
    # an underlying library raises as a different type.
    import integrations.ical.parser as parser_mod

    def _boom(_calendar: object) -> object:
        raise TypeError("simulated expander failure")

    monkeypatch.setattr(parser_mod.recurring_ical_events, "of", _boom)
    with pytest.raises(ValueError):
        _parse(_ics(_event("a", "20260701", "20260705")))


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
