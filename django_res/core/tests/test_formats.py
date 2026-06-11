"""Unit tests for `core.formats` — customer-facing merge-field formatting."""

from __future__ import annotations

from datetime import UTC, date, datetime

from core.formats import format_date


def test_format_date_renders_long_form() -> None:
    assert format_date(date(2025, 7, 8)) == "8 July 2025"


def test_format_date_no_zero_padding() -> None:
    assert format_date(date(2026, 1, 1)) == "1 January 2026"


def test_format_date_accepts_datetime() -> None:
    assert format_date(datetime(2025, 7, 8, 14, 30, tzinfo=UTC)) == "8 July 2025"
