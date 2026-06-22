"""Tests for the E.164 phone-normalization helper (`reservations.phone`)."""

from __future__ import annotations

from reservations.phone import to_e164


class TestToE164:
    def test_international_input_round_trips(self) -> None:
        assert to_e164("+44 7911 123456") == "+447911123456"

    def test_national_number_with_region_resolves(self) -> None:
        assert to_e164("07911 123456", region="GB") == "+447911123456"

    def test_national_number_with_calling_code_resolves(self) -> None:
        # Legacy stores a numeric calling code (e.g. "44"), not an ISO region.
        assert to_e164("07911 123456", country_code="44") == "+447911123456"

    def test_unparseable_input_passes_through_trimmed(self) -> None:
        assert to_e164("  not a phone  ") == "not a phone"

    def test_unparseable_but_numeric_passes_through(self) -> None:
        # No region/calling code to anchor it — keep the raw rather than guess.
        assert to_e164("12345") == "12345"

    def test_empty_and_none_become_empty_string(self) -> None:
        assert to_e164("") == ""
        assert to_e164("   ") == ""
        assert to_e164(None) == ""
