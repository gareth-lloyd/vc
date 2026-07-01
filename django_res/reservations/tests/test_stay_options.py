"""StayOptionsService — changeover-block stay options for the quote builder.

Pure-helper unit tests (no DB) plus service/endpoint tests against the
fixture pricing graph (Summer 2026 plan, £200/night rule covering
2026-06-01..08-31; 2026-07-04 and 2026-07-11 are Saturdays).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
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
    from accounts.models import Person
    from pricing.models import Currency, RateCard, RatePlan, RateRule
    from properties.models import Property
    from reservations.models import TermsVersion


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


def _occupancy_card(card: RateCard) -> None:
    """Seed `card` with three sibling occupancy brackets (£100/£140/£160 a
    night) over the fixture Summer-2026 window — a fan-out villa."""
    from pricing.models import RateRule as RateRuleModel

    common = {"card": card, "date_from": date(2026, 6, 1), "date_to": date(2026, 8, 31)}
    RateRuleModel.objects.create(**common, min_party=1, max_party=8, nightly=Decimal("100.00"))
    RateRuleModel.objects.create(**common, min_party=9, max_party=12, nightly=Decimal("140.00"))
    RateRuleModel.objects.create(**common, min_party=13, max_party=16, nightly=Decimal("160.00"))


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

    def test_plan_boundary_inside_window_still_offers_blocks(
        self, property_: Property, plan: RatePlan, rate_rule: RateRule
    ) -> None:
        # The plan covers the preferred dates but ends inside the widened
        # window, so no single context covers the window: the bounds clamp is
        # skipped and the quote loads its own context — blocks still come back
        # and the default still prices.
        _sat_changeover(property_)
        plan.effective_to = date(2026, 7, 12)
        plan.save(update_fields=["effective_to"])

        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 5), date(2026, 7, 15))],
            flex_days=3,
        )

        assert result["available"] is True
        assert result["date_from"] == "2026-07-04"
        assert result["total"] == "1400.00"
        assert [(o["date_from"], o["is_default"]) for o in result["stay_options"]] == [
            ("2026-07-04", True),
            ("2026-07-11", False),
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

    def test_multi_week_window_offers_one_block_per_week(
        self,
        property_: Property,
        rate_rule: RateRule,
        customer: Person,
        gbp: Currency,
        terms: TermsVersion,
    ) -> None:
        # "Any week around early July": Sat 4 Jul → Sat 11 Jul ± 21 days
        # widens the window to Sat 13 Jun → Sat 1 Aug, which admits seven
        # 7-night Saturday blocks. The preferred arrival stays the default,
        # and each block carries its own availability flag.
        _sat_changeover(property_)
        make_occupying_booking(
            property=property_,
            person=customer,
            currency=gbp,
            terms=terms,
            date_from=date(2026, 6, 22),
            date_to=date(2026, 6, 26),
        )
        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 4), date(2026, 7, 11))],
            flex_days=21,
        )
        assert result["available"] is True
        assert result["date_from"] == "2026-07-04"
        assert result["total"] == "1400.00"
        assert [
            (o["date_from"], o["is_default"], o["is_available"]) for o in result["stay_options"]
        ] == [
            ("2026-06-13", False, True),
            ("2026-06-20", False, False),
            ("2026-06-27", False, True),
            ("2026-07-04", True, True),
            ("2026-07-11", False, True),
            ("2026-07-18", False, True),
            ("2026-07-25", False, True),
        ]
        assert all(o["nights"] == 7 for o in result["stay_options"])

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
        customer: Person,
        gbp: Currency,
        terms: TermsVersion,
    ) -> None:
        # A booking departing 11 Jul blocks the 4→11 block but NOT the block
        # arriving 11 Jul — back-to-back changeover is sellable.
        _sat_changeover(property_)
        make_occupying_booking(
            property=property_,
            person=customer,
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

    # -- GAP-044 occupancy fan-out --------------------------------------

    def test_occupancy_property_fans_out_all_bands(
        self, property_: Property, plan: RatePlan, card: RateCard
    ) -> None:
        """An occupancy-priced villa returns every covering band as its own
        priced entry (sorted by `min_party`), each at its representative party
        `max(1, min_party)` — the builder renders one default-checked line per."""
        _sat_changeover(property_)
        _occupancy_card(card)

        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 4), date(2026, 7, 11), adults=2)],
            flex_days=0,
        )

        assert result["available"] is True
        assert result["occupancy_bands"] == [
            {
                "min_party": 1,
                "max_party": 8,
                "adults": 1,
                "total": "700.00",
                "currency_code": "GBP",
                "is_projected": False,
                "is_poa": False,
                "error_code": None,
            },
            {
                "min_party": 9,
                "max_party": 12,
                "adults": 9,
                "total": "980.00",
                "currency_code": "GBP",
                "is_projected": False,
                "is_poa": False,
                "error_code": None,
            },
            {
                "min_party": 13,
                "max_party": 16,
                "adults": 13,
                "total": "1120.00",
                "currency_code": "GBP",
                "is_projected": False,
                "is_poa": False,
                "error_code": None,
            },
        ]

    def test_single_band_property_has_no_fan_out(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        """A single-bracket villa keeps its one headline line — no fan-out (the
        >=2-band threshold lives here, not in the enumerator)."""
        _sat_changeover(property_)

        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 4), date(2026, 7, 11))],
            flex_days=0,
        )

        assert result["available"] is True
        assert result["occupancy_bands"] == []

    def test_bands_shown_even_when_searched_party_out_of_bracket(
        self, property_: Property, plan: RatePlan, card: RateCard
    ) -> None:
        """B2: the fan-out is independent of the searched party. A party fitting
        no bracket makes the *headline* quote unavailable, yet every covering
        band still fans out (the builder shows the bands, not an error)."""
        _sat_changeover(property_)
        _occupancy_card(card)

        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 4), date(2026, 7, 11), adults=20)],
            flex_days=0,
        )

        assert result["available"] is False
        assert result["error_code"] == "party_out_of_range"
        assert [
            (b["min_party"], b["max_party"], b["total"]) for b in result["occupancy_bands"]
        ] == [(1, 8, "700.00"), (9, 12, "980.00"), (13, 16, "1120.00")]

    def test_poa_band_is_flagged_not_dropped(
        self, property_: Property, plan: RatePlan, card: RateCard
    ) -> None:
        """A POA / no-rate band surfaces flagged (`total=None`, `is_poa`) with a
        resolved display currency — never silently dropped (Q-013)."""
        from pricing.models import RateRule as RateRuleModel

        _sat_changeover(property_)
        common = {"card": card, "date_from": date(2026, 6, 1), "date_to": date(2026, 8, 31)}
        RateRuleModel.objects.create(**common, min_party=1, max_party=8, nightly=Decimal("100.00"))
        RateRuleModel.objects.create(**common, min_party=9, max_party=12, nightly=None, is_poa=True)

        [result] = StayOptionsService.search(
            requests=[_entry(property_, date(2026, 7, 4), date(2026, 7, 11), adults=2)],
            flex_days=0,
        )

        bands = result["occupancy_bands"]
        assert [(b["min_party"], b["total"], b["is_poa"], b["error_code"]) for b in bands] == [
            (1, "700.00", False, None),
            (9, None, True, "no_rate_available"),
        ]
        # The POA band still resolves a display currency from the covering plan.
        assert bands[1]["currency_code"] == "GBP"

    def test_band_fan_out_query_budget_reuses_context(
        self, property_: Property, plan: RatePlan, card: RateCard
    ) -> None:
        """M4: the three per-band re-prices reuse the one window context — no
        rate/plan/card reload per band. Pin a ceiling so a per-band context
        reload can't creep in unnoticed (each band's residual cost is only the
        extras/discount/changeover/service lookups `quote()` always does — the
        service lookup for the "Includes:" line is GAP-037; the headline + 3 band
        quotes each pay it). Headroom stays under a per-band context reload (~+3
        queries/band), which is what this guards against."""
        _sat_changeover(property_)
        _occupancy_card(card)
        entry = _entry(property_, date(2026, 7, 4), date(2026, 7, 11), adults=2)
        StayOptionsService.search(requests=[entry], flex_days=0)  # warm content types

        with assert_max_queries(28):
            StayOptionsService.search(requests=[entry], flex_days=0)


@pytest.mark.django_db
class TestWeeklyPrices:
    """`StayOptionsService.weekly_prices` — GAP-030 timeline price strip."""

    def test_fixed_changeover_prices_each_week(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        # Sat 4 Jul → Sat 1 Aug: Saturday arrivals 4/11/18/25 Jul each fit a
        # full 7-night block in the window, priced at £200 x 7.
        _sat_changeover(property_)
        [result] = StayOptionsService.weekly_prices(
            property_ids=[property_.pk],
            window_from=date(2026, 7, 4),
            window_to=date(2026, 8, 1),
        )
        assert result["property_id"] == property_.pk
        assert result["changeover_day"] == "sat"
        assert [(w["week_start"], w["week_end"], w["price"]) for w in result["weeks"]] == [
            ("2026-07-04", "2026-07-11", "1400.00"),
            ("2026-07-11", "2026-07-18", "1400.00"),
            ("2026-07-18", "2026-07-25", "1400.00"),
            ("2026-07-25", "2026-08-01", "1400.00"),
        ]
        assert all(w["currency_code"] == "GBP" for w in result["weeks"])
        assert all(w["is_projected"] is False for w in result["weeks"])
        assert all(w["is_poa"] is False for w in result["weeks"])
        assert all(w["error_code"] is None for w in result["weeks"])

    def test_flexible_changeover_returns_no_weeks(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        # No ChangeOverRule → 'any' changeover: deferred (GAP-025 / Q-022).
        [result] = StayOptionsService.weekly_prices(
            property_ids=[property_.pk],
            window_from=date(2026, 7, 4),
            window_to=date(2026, 8, 1),
        )
        assert result["changeover_day"] is None
        assert result["weeks"] == []

    def test_no_rate_emits_incomplete_shape_not_500(self, property_: Property) -> None:
        # Fixed changeover but no rate plan → each week is incomplete-priced,
        # never an exception.
        _sat_changeover(property_)
        [result] = StayOptionsService.weekly_prices(
            property_ids=[property_.pk],
            window_from=date(2026, 7, 4),
            window_to=date(2026, 7, 18),
        )
        assert result["changeover_day"] == "sat"
        assert len(result["weeks"]) == 2
        for week in result["weeks"]:
            assert week["price"] is None
            assert week["error_code"] == "no_rate_available"
            assert week["is_poa"] is False
            assert week["currency_code"] is None

    def test_poa_week_is_flagged(self, property_: Property, plan: RatePlan, card: RateCard) -> None:
        from pricing.models import RateRule as RateRuleModel

        _sat_changeover(property_)
        RateRuleModel.objects.create(
            card=card,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 8, 31),
            min_party=1,
            max_party=8,
            nightly=None,
            is_poa=True,
        )
        [result] = StayOptionsService.weekly_prices(
            property_ids=[property_.pk],
            window_from=date(2026, 7, 4),
            window_to=date(2026, 7, 18),
        )
        assert result["weeks"]
        for week in result["weeks"]:
            assert week["price"] is None
            assert week["is_poa"] is True
            assert week["error_code"] == "no_rate_available"
            # POA still resolves a display currency (from the covering plan).
            assert week["currency_code"] == "GBP"

    def test_future_year_prices_are_flagged_as_projected_guides(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        # 2027 has no plan; prices project from the 2026 rates and read as
        # guides (is_projected), never firm quotes.
        ChangeOverRule.objects.create(
            property=property_,
            day=PrefilledChangeOverDay.SAT,
            starts_on=date(2027, 1, 1),
            ends_on=date(2027, 12, 31),
        )
        [result] = StayOptionsService.weekly_prices(
            property_ids=[property_.pk],
            window_from=date(2027, 7, 3),
            window_to=date(2027, 7, 31),
        )
        assert result["changeover_day"] == "sat"
        assert result["weeks"]
        for week in result["weeks"]:
            assert week["is_projected"] is True
            assert week["price"] is not None
            assert week["error_code"] is None

    def test_unknown_property_returns_empty_strip(self, db: None) -> None:
        [result] = StayOptionsService.weekly_prices(
            property_ids=[999_999],
            window_from=date(2026, 7, 4),
            window_to=date(2026, 8, 1),
        )
        assert result == {"property_id": 999_999, "changeover_day": None, "weeks": []}

    def test_query_count_does_not_reload_context_per_week(
        self, property_: Property, rate_rule: RateRule
    ) -> None:
        # The expensive plan/card/rule context loads ONCE per property and
        # every week's quote reuses it (the AC's "no N-times-weeks per-villa engine
        # calls"). The residual per-week cost is the extras/discount/changeover/
        # service lookups quote() always does — a PricingContext only caches the
        # rate graph. Pin a ceiling well under the ~30 a per-week context *reload*
        # would cost over this 4-week window, so a regression there can't hide.
        _sat_changeover(property_)
        with assert_max_queries(24):
            StayOptionsService.weekly_prices(
                property_ids=[property_.pk],
                window_from=date(2026, 7, 4),
                window_to=date(2026, 8, 1),
            )


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

    def test_multi_week_flex_accepted(
        self,
        api_client: APIClient,
        staff: User,
        property_: Property,
        rate_rule: RateRule,
    ) -> None:
        # The widest window (±21 days) round-trips: seven Saturday blocks.
        _sat_changeover(property_)
        api_client.force_authenticate(staff)
        body = self._body(property_, flex_days=21)
        body["requests"][0].update({"date_from": "2026-07-04", "date_to": "2026-07-11"})  # type: ignore[index]
        response = api_client.post(self.URL, body, format="json")
        assert response.status_code == 200
        [quote] = response.data["quotes"]
        assert len(quote["stay_options"]) == 7

    def test_flex_days_out_of_range_rejected(
        self, api_client: APIClient, staff: User, property_: Property
    ) -> None:
        api_client.force_authenticate(staff)
        response = api_client.post(self.URL, self._body(property_, flex_days=22), format="json")
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
        # once per entry, shared between the bounds clamp and the quote. Two
        # single-query enrichments ride on top of the base clamp+quote: the
        # GAP-037 PropertyService lookup for the "Includes:" line, and GAP-044's
        # occupancy-band enumeration (`covering_bands` resolves the changeover
        # day once even on a single-band villa that then fans out nothing). Pin
        # so a per-option or per-band context *reload* can't creep in unnoticed.
        _sat_changeover(property_)
        api_client.force_authenticate(staff)
        body = self._body(property_)
        api_client.post(self.URL, body, format="json")  # warm content types etc.
        with assert_max_queries(14):
            response = api_client.post(self.URL, body, format="json")
        assert response.status_code == 200


@pytest.mark.django_db
class TestWeeklyPricesEndpoint:
    URL = "/api/v1/availability/weekly-prices"

    def _params(self, property_: Property, **overrides: str) -> dict[str, str]:
        params = {
            "property_ids": str(property_.pk),
            "from": "2026-07-04",
            "to": "2026-08-01",
        }
        params.update(overrides)
        return params

    def test_requires_staff(self, api_client: APIClient, property_: Property) -> None:
        response = api_client.get(self.URL, self._params(property_))
        assert response.status_code in (401, 403)

    def test_returns_weekly_prices(
        self,
        api_client: APIClient,
        staff: User,
        property_: Property,
        rate_rule: RateRule,
    ) -> None:
        _sat_changeover(property_)
        api_client.force_authenticate(staff)
        response = api_client.get(self.URL, self._params(property_))
        assert response.status_code == 200
        [row] = response.data["properties"]
        assert row["property_id"] == property_.pk
        assert row["changeover_day"] == "sat"
        assert len(row["weeks"]) == 4
        assert row["weeks"][0]["price"] == "1400.00"
        assert row["weeks"][0]["currency_code"] == "GBP"

    def test_missing_params_is_400(self, api_client: APIClient, staff: User) -> None:
        api_client.force_authenticate(staff)
        response = api_client.get(self.URL, {"property_ids": "", "from": "", "to": ""})
        assert response.status_code == 400

    def test_too_many_ids_is_400(self, api_client: APIClient, staff: User) -> None:
        api_client.force_authenticate(staff)
        ids = ",".join(str(n) for n in range(1, 52))  # 51 > 50 cap
        response = api_client.get(
            self.URL, {"property_ids": ids, "from": "2026-07-04", "to": "2026-08-01"}
        )
        assert response.status_code == 400
