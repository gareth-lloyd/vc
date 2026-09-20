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

    def test_trailing_decimal_zeros_are_stripped_before_parsing(self) -> None:
        # GAP-118 §2: the xlsx cell is literally the string "+44 7985414214.00"
        # (openpyxl type `str`, format General), so no numeric coercion applies.
        assert to_e164("+44 7985414214.00") == "+447985414214"
        assert to_e164("07985414214.0", region="GB") == "+447985414214"

    def test_trailing_decimal_zeros_survive_on_unparseable_input(self) -> None:
        # Only a *valid* number is rewritten; junk passes through verbatim.
        assert to_e164("call office.00") == "call office.00"
        assert to_e164("12345.0") == "12345.0"

    def test_dot_separated_numbers_keep_their_trailing_zero_group(self) -> None:
        # French/Belgian/Swiss numbers are conventionally dot-separated; a
        # final "00" group is a real part of the number, not a spreadsheet
        # tail. Stripping it here once turned +390669820 into +39066982.
        assert to_e164("04.93.12.34.00", region="FR") == "+33493123400"
        assert to_e164("+33 4.93.12.34.00") == "+33493123400"
        assert to_e164("+39 06.6982.0") == "+390669820"

    def test_empty_and_none_become_empty_string(self) -> None:
        assert to_e164("") == ""
        assert to_e164("   ") == ""
        assert to_e164(None) == ""
