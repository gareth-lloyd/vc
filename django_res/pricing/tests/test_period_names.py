"""Unit tests for `pricing.services.period_names` — placeholder name derivation."""

from __future__ import annotations

from datetime import date

from pricing.services.period_names import derive_period_name


def test_same_month() -> None:
    assert derive_period_name(date(2026, 7, 3), date(2026, 7, 21)) == "3\u201321 Jul"


def test_cross_month() -> None:
    assert derive_period_name(date(2026, 7, 3), date(2026, 8, 21)) == "3 Jul\u201321 Aug"


def test_cross_year() -> None:
    assert derive_period_name(date(2026, 12, 27), date(2027, 1, 3)) == "27 Dec 2026\u20133 Jan 2027"


def test_single_day() -> None:
    assert derive_period_name(date(2026, 7, 3), date(2026, 7, 3)) == "3 Jul"


def test_locale_independent() -> None:
    from django.utils import translation

    with translation.override("el"):
        assert derive_period_name(date(2026, 7, 3), date(2026, 8, 21)) == "3 Jul\u201321 Aug"
