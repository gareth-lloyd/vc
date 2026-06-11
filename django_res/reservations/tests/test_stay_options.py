"""StayOptionsService — changeover-block stay options for the quote builder.

Pure-helper unit tests (no DB) plus service/endpoint tests against the
fixture pricing graph (Summer 2026 plan, £200/night rule covering
2026-06-01..08-31; 2026-07-04 and 2026-07-11 are Saturdays).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.tests import assert_max_queries
from properties.enums import PrefilledChangeOverDay
from properties.models import ChangeOverRule
from reservations.factories import make_occupying_booking
from reservations.models import BookingHold
from reservations.services.stay_options import (
    StayOptionsService,
    block_nights,
    candidate_blocks,
    pick_default,
)

if TYPE_CHECKING:
    from pricing.models import Currency, RateRule
    from properties.models import Property
    from reservations.models import Guest, TermsVersion


# ----------------------------------------------------------------------
# Pure helpers (no DB)
# ----------------------------------------------------------------------


class TestBlockNights:
    def test_rounds_to_nearest_multiple_of_seven(self) -> None:
        # 11 nights → 14 (|11-14|=3 beats |11-7|=4) when the window allows.
        assert block_nights(11, 25) == 14

    def test_rounds_down_when_shorter_multiple_is_nearer(self) -> None:
        assert block_nights(10, 16) == 7

    def test_floors_short_stays_to_one_week(self) -> None:
        # A 3-night request at a fixed-changeover villa quotes a full week.
        assert block_nights(3, 9) == 7

    def test_window_constrains_the_choice(self) -> None:
        # Nearest multiple to 11 is 14, but a 13-night window only fits 7.
        assert block_nights(11, 13) == 7

    def test_none_when_no_multiple_fits_the_window(self) -> None:
        assert block_nights(3, 5) is None

    def test_card_bounds_filter_the_candidates(self) -> None:
        assert block_nights(10, 30, min_nights=12) == 14
        assert block_nights(20, 30, max_nights=15) == 14

    def test_none_when_bounds_exclude_every_multiple(self) -> None:
        assert block_nights(10, 30, max_nights=6) is None


class TestCandidateBlocks:
    def test_one_block_per_matching_weekday_arrival(self) -> None:
        # Sat changeover, 7-night blocks in a Thu 2 Jul → Sat 18 Jul window.
        blocks = candidate_blocks(date(2026, 7, 2), date(2026, 7, 18), 5, 7)
        assert blocks == [
            (date(2026, 7, 4), date(2026, 7, 11)),
            (date(2026, 7, 11), date(2026, 7, 18)),
        ]

    def test_block_must_fit_inside_the_window(self) -> None:
        # Arrivals may only run to window_to - nights: no Saturday by 3 Jul.
        assert candidate_blocks(date(2026, 7, 2), date(2026, 7, 10), 5, 7) == []


class TestPickDefault:
    def test_closest_arrival_to_preferred_wins(self) -> None:
        blocks = [
            (date(2026, 7, 4), date(2026, 7, 11)),
            (date(2026, 7, 11), date(2026, 7, 18)),
        ]
        assert pick_default(blocks, date(2026, 7, 5)) == 0
        assert pick_default(blocks, date(2026, 7, 9)) == 1

    def test_tie_prefers_the_earlier_arrival(self) -> None:
        blocks = [
            (date(2026, 7, 4), date(2026, 7, 11)),
            (date(2026, 7, 10), date(2026, 7, 17)),
        ]
        # 7 Jul is 3 days from both arrivals.
        assert pick_default(blocks, date(2026, 7, 7)) == 0


# ----------------------------------------------------------------------
# Service orchestration (DB)
# ----------------------------------------------------------------------


def _sat_changeover(property_: Property) -> None:
    ChangeOverRule.objects.create(
        property=property_,
        day=PrefilledChangeOverDay.SAT,
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 8, 31),
    )


def _entry(
    property_: Property,
    date_from: date,
    date_to: date,
    adults: int = 2,
    children: int = 0,
) -> dict[str, object]:
    return {
        "property_id": property_.pk,
        "date_from": date_from,
        "date_to": date_to,
        "adults": adults,
        "children": children,
    }


@pytest.mark.django_db
class TestStayOptionsSearch:
    def test_unconstrained_property_prices_preferred_dates_single_option(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 4), date(2026, 7, 11))],
            flex_days=3,
        )
        assert result["available"] is True
        assert result["total"] == "1400.00"
        assert result["date_from"] == "2026-07-04"
        assert result["stay_options"] == [
            {
                "date_from": "2026-07-04",
                "date_to": "2026-07-11",
                "nights": 7,
                "is_default": True,
                "is_available": True,
            }
        ]

    def test_fixed_changeover_offers_each_fitting_block(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        # Sun 5 Jul → Wed 15 Jul (10 nights) ± 3 days at a Sat-changeover
        # villa: the window Thu 2 Jul → Sat 18 Jul admits 7-night Sat blocks
        # at 4 Jul and 11 Jul. Default = closest arrival to the preferred one.
        _sat_changeover(property_)
        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 5), date(2026, 7, 15))],
            flex_days=3,
        )
        assert result["available"] is True
        # The default block is the one actually priced.
        assert result["date_from"] == "2026-07-04"
        assert result["date_to"] == "2026-07-11"
        assert result["total"] == "1400.00"
        assert [
            (o["date_from"], o["date_to"], o["is_default"]) for o in result["stay_options"]
        ] == [
            ("2026-07-04", "2026-07-11", True),
            ("2026-07-11", "2026-07-18", False),
        ]

    def test_flex_zero_on_aligned_request_yields_single_block(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        _sat_changeover(property_)
        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 4), date(2026, 7, 11))],
            flex_days=0,
        )
        assert result["available"] is True
        assert len(result["stay_options"]) == 1
        assert result["stay_options"][0]["is_default"] is True

    def test_no_fitting_block_falls_back_to_preferred_dates(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        # 5 nights with flex 0: no 7-night multiple fits the window, so the
        # engine prices the preferred dates exactly as today.
        _sat_changeover(property_)
        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 4), date(2026, 7, 9))],
            flex_days=0,
        )
        assert result["available"] is True
        assert result["date_from"] == "2026-07-04"
        assert result["date_to"] == "2026-07-09"
        assert len(result["stay_options"]) == 1
        assert result["stay_options"][0]["nights"] == 5

    def test_availability_flags_use_half_open_overlap(
        self,
        property_: Property,
        rate_rule: RateRule,
        guest: Guest,
        gbp: Currency,
        terms: TermsVersion,
    ) -> None:
        # A booking departing 11 Jul blocks the 4→11 block but NOT the block
        # arriving 11 Jul — back-to-back changeover is sellable.
        _sat_changeover(property_)
        make_occupying_booking(
            property=property_,
            guest=guest,
            currency=gbp,
            terms=terms,
            date_from=date(2026, 7, 6),
            date_to=date(2026, 7, 11),
        )
        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 5), date(2026, 7, 15))],
            flex_days=3,
        )
        assert [(o["date_from"], o["is_available"]) for o in result["stay_options"]] == [
            ("2026-07-04", False),
            ("2026-07-11", True),
        ]

    def test_live_hold_flags_block_unavailable(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        _sat_changeover(property_)
        BookingHold.objects.create(
            property=property_,
            date_from=date(2026, 7, 12),
            date_to=date(2026, 7, 14),
            expires_at=timezone.now() + timedelta(days=2),
        )
        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 5), date(2026, 7, 15))],
            flex_days=3,
        )
        assert [(o["date_from"], o["is_available"]) for o in result["stay_options"]] == [
            ("2026-07-04", True),
            ("2026-07-11", False),
        ]

    def test_no_rate_entry_matches_bulk_error_shape(self, property_: Property) -> None:
        # No plan at all → Q-013 manual-quote entry; currency unresolvable.
        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 4), date(2026, 7, 11))],
            flex_days=0,
        )
        assert result["available"] is False
        assert result["error_code"] == "no_rate_available"
        assert "error_detail" in result
        assert result["currency_code"] is None
        assert "hero_image_url" in result

    def test_unknown_property_returns_unavailable_stub(self, db: None) -> None:
        [result] = StayOptionsService.search(
            requests=[
                {
                    "property_id": 999_999,
                    "date_from": date(2026, 7, 4),
                    "date_to": date(2026, 7, 11),
                    "adults": 2,
                    "children": 0,
                }
            ],
            flex_days=0,
        )
        assert result == {"property_id": 999_999, "available": False}


# ----------------------------------------------------------------------
# Endpoint
# ----------------------------------------------------------------------


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def staff(db: None) -> User:
    return User.objects.create_user(
        is_staff=True,
        email="stay-options-staff@example.com",
        password="x",
        role=StaffRole.RESERVATIONS,
    )


@pytest.mark.django_db
class TestSearchOptionsEndpoint:
    URL = "/api/v1/quotations:search-options"

    def _body(self, property_: Property, **overrides: object) -> dict[str, object]:
        body: dict[str, object] = {
            "flex_days": 3,
            "requests": [
                {
                    "property_id": property_.pk,
                    "date_from": "2026-07-05",
                    "date_to": "2026-07-15",
                    "adults": 2,
                    "children": 0,
                }
            ],
        }
        body.update(overrides)
        return body

    def test_requires_staff(self, api_client: APIClient, property_: Property) -> None:
        response = api_client.post(self.URL, self._body(property_), format="json")
        assert response.status_code in (401, 403)

    def test_round_trip(
        self,
        api_client: APIClient,
        staff: User,
        property_: Property,
        rate_rule: RateRule,
    ) -> None:
        _sat_changeover(property_)
        api_client.force_authenticate(staff)
        response = api_client.post(self.URL, self._body(property_), format="json")
        assert response.status_code == 200
        [quote] = response.data["quotes"]
        assert quote["available"] is True
        assert quote["total"] == "1400.00"
        assert len(quote["stay_options"]) == 2
        # Enrichment flows through from the engine breakdown untouched.
        assert quote["changeover_day"] == "sat"
        assert quote["inclusion"] == ""

    def test_flex_days_out_of_range_rejected(
        self, api_client: APIClient, staff: User, property_: Property
    ) -> None:
        api_client.force_authenticate(staff)
        response = api_client.post(self.URL, self._body(property_, flex_days=4), format="json")
        assert response.status_code == 400

    def test_unknown_currency_is_a_404(
        self, api_client: APIClient, staff: User, property_: Property
    ) -> None:
        # Parity with /pricing:quote-bulk's currency resolution.
        api_client.force_authenticate(staff)
        response = api_client.post(self.URL, self._body(property_, currency="XXX"), format="json")
        assert response.status_code == 404

    def test_query_count_does_not_scale_per_stay_option(
        self,
        api_client: APIClient,
        staff: User,
        property_: Property,
        rate_rule: RateRule,
    ) -> None:
        # Properties + availability are batched; the per-entry cost is the
        # engine itself (15 queries for one entry today). Pin so a per-option or
        # per-block query can't creep in unnoticed.
        _sat_changeover(property_)
        api_client.force_authenticate(staff)
        body = self._body(property_)
        api_client.post(self.URL, body, format="json")  # warm content types etc.
        with assert_max_queries(15):
            response = api_client.post(self.URL, body, format="json")
        assert response.status_code == 200
