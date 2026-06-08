"""Tests for the E.164 phone-normalization helper (`reservations.phone`)."""

from __future__ import annotations

import pytest

from reservations.models import Guest
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


@pytest.mark.django_db
class TestGuestSavesNormalizedPhone:
    def test_save_normalizes_international_phone(self) -> None:
        guest = Guest.objects.create(
            first_name="A",
            last_name="B",
            email="a@b.com",
            phone="+44 7911 123456",
        )
        guest.refresh_from_db()
        assert guest.phone == "+447911123456"

    def test_save_leaves_unanchorable_national_phone_untouched(self) -> None:
        guest = Guest.objects.create(
            first_name="A",
            last_name="B",
            email="a@b.com",
            phone="07911 123456",
        )
        guest.refresh_from_db()
        # No region on the Guest write path, so it can't be resolved — kept raw.
        assert guest.phone == "07911 123456"
