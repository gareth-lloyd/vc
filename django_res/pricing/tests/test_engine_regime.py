"""Period-first plan selection (GAP-110 U3).

The engine no longer gates on the plan's date envelope: it fetches the active
periods (of active plans) touching the stay nights and infers the plan from
them. A stay no period touches projects; a stay two same-currency plans touch
(a GROSS and a NET regime) is a `MultiRegimeStay`; with no currency asked for,
the currency whose periods cover the most nights wins, then the settings currency,
then the lowest plan pk.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from core.enums import StaffRole
from core.exceptions import MultiRegimeStay, NoRateAvailable
from pricing.models import Currency, RateBand, RatePeriod, RatePlan
from pricing.services.engine import PricingEngine
from properties.enums import PriceBasis
from properties.models.settings import PropertySettings

if TYPE_CHECKING:
    from properties.models import Property


def _priced_period(
    plan: RatePlan,
    date_from: date,
    date_to: date,
    *,
    nightly: str = "200.00",
    name: str = "Period",
    **overrides: object,
) -> RatePeriod:
    period = RatePeriod.objects.create(
        plan=plan, name=name, date_from=date_from, date_to=date_to, **overrides
    )
    RateBand.objects.create(period=period, min_party=1, max_party=8, nightly=Decimal(nightly))
    return period


def _plan(property_: Property, currency: Currency, **overrides: object) -> RatePlan:
    defaults: dict[str, object] = {
        "name": f"{currency.code} rates",
        "prices_by_occupancy": True,
    }
    return RatePlan.objects.create(
        property=property_, currency=currency, **{**defaults, **overrides}
    )


# ---------------------------------------------------------------------------
# Envelope is gone: the period is the date authority
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_new_years_day_checkout_prices_on_the_period_ending_31_dec(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    """The priced period ends 31 Dec (inclusive) and the stay checks out 1 Jan
    (exclusive): the old whole-stay envelope gate refused it, although every
    night is priced."""
    _priced_period(plan, date(2026, 12, 1), date(2026, 12, 31), nightly="100.00")

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 12, 29),
        date_to=date(2027, 1, 1),
        party=2,
        currency=gbp,
        allow_projection=False,
    )

    assert quote.is_projected is False
    assert quote.rate_subtotal == Decimal("300.00")


@pytest.mark.django_db
def test_context_carries_only_the_plans_periods_touching_the_stay(
    property_: Property, gbp: Currency, plan: RatePlan, period: RatePeriod
) -> None:
    """A plan is a multi-year bucket (the loader regroups every legacy season
    of a villa + currency onto one), so the context carries the periods that
    touch the stay — never another year's, whose min/max nights would
    otherwise leak into `stay_length_bounds` — and never an inactive one."""
    period.date_to = date(2026, 8, 19)
    period.save(update_fields=["date_to"])
    last_year = _priced_period(plan, date(2025, 6, 1), date(2025, 8, 31), name="Last year")
    september = _priced_period(plan, date(2026, 9, 1), date(2026, 9, 30), name="September")
    RatePeriod.objects.create(
        plan=plan,
        name="Withdrawn",
        date_from=date(2026, 8, 20),
        date_to=date(2026, 8, 31),
        is_active=False,
    )

    june = PricingEngine.load_context(
        property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 17), currency=gbp
    )
    assert june is not None
    assert june.plan == plan
    assert [p.pk for p in june.periods] == [period.pk]

    straddle = PricingEngine.load_context(
        property_, date_from=date(2026, 8, 15), date_to=date(2026, 9, 5), currency=gbp
    )
    assert straddle is None  # the withdrawn period leaves 20-31 Aug uncovered

    september_stay = PricingEngine.load_context(
        property_, date_from=date(2026, 9, 5), date_to=date(2026, 9, 12), currency=gbp
    )
    assert september_stay is not None
    assert [p.pk for p in september_stay.periods] == [september.pk]
    assert last_year.pk not in {p.pk for p in september_stay.periods}


@pytest.mark.django_db
def test_stay_no_period_touches_projects(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateBand
) -> None:
    """Gap policy: no real night → project (the plan's envelope is irrelevant)."""
    assert (
        PricingEngine.load_context(
            property_, date_from=date(2027, 6, 5), date_to=date(2027, 6, 12), currency=gbp
        )
        is None
    )
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2027, 6, 5),
        date_to=date(2027, 6, 12),
        party=2,
        currency=gbp,
    )
    assert quote.is_projected is True
    assert quote.breakdown["projection"]["source_year"] == 2026


@pytest.mark.django_db
def test_unpriced_dates_of_a_partly_priced_year_project_from_the_prior_year(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateBand
) -> None:
    """2026 only prices Jun-Aug; an October 2026 stay projects from 2025 instead
    of failing on the 2026 plan as the old envelope gate made it."""
    _priced_period(plan, date(2025, 1, 1), date(2025, 12, 31), nightly="150.00", name="2025")

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 10, 3),
        date_to=date(2026, 10, 10),
        party=2,
        currency=gbp,
    )

    assert quote.is_projected is True
    assert quote.breakdown["projection"]["source_year"] == 2025


@pytest.mark.django_db
def test_periodless_fallback_plan_no_longer_prices(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    """A plan with `fallback_nightly` and no periods is not a pricing source
    (GAP-110 decision 1): fallback fills the gaps of a partly-covered stay, it
    does not conjure a stay out of nothing."""
    plan.fallback_nightly = Decimal("99.00")
    plan.save(update_fields=["fallback_nightly"])

    assert (
        PricingEngine.load_context(
            property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 13), currency=gbp
        )
        is None
    )
    with pytest.raises(NoRateAvailable):
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 6, 10),
            date_to=date(2026, 6, 13),
            party=4,
            currency=gbp,
            allow_projection=False,
        )


# ---------------------------------------------------------------------------
# Two regimes touching one stay
# ---------------------------------------------------------------------------
@pytest.fixture
def net_plan(property_: Property, gbp: Currency) -> RatePlan:
    """A NET-basis plan in `plan`'s currency owning September 2026."""
    net = _plan(property_, gbp, name="GBP net", price_basis=PriceBasis.NET)
    _priced_period(net, date(2026, 9, 1), date(2026, 9, 30), nightly="120.00", name="Sept net")
    return net


@pytest.mark.django_db
def test_gross_and_net_plans_touching_one_stay_raise_multi_regime_stay(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateBand, net_plan: RatePlan
) -> None:
    with pytest.raises(MultiRegimeStay) as excinfo:
        PricingEngine.quote(
            property=property_,
            date_from=date(2026, 8, 30),
            date_to=date(2026, 9, 2),
            party=2,
            currency=gbp,
        )

    exc = excinfo.value
    assert isinstance(exc, NoRateAvailable)
    assert exc.code == "no_rate_available"
    assert property_.name in str(exc)
    assert plan.name in str(exc)
    assert net_plan.name in str(exc)


@pytest.mark.django_db
def test_multi_regime_stay_is_a_409_no_rate_available(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateBand, net_plan: RatePlan
) -> None:
    """The API surface keeps the `no_rate_available` code so every existing
    front-end branch degrades safely; the detail is the staff-readable one."""
    staff = User.objects.create_user(
        is_staff=True, email="regime@example.com", password="x", role=StaffRole.RESERVATIONS
    )
    client = APIClient()
    client.force_login(staff)

    response = client.post(
        "/api/v1/pricing:quote",
        data={
            "property_id": property_.pk,
            "date_from": "2026-08-30",
            "date_to": "2026-09-02",
            "adults": 2,
        },
        format="json",
    )

    assert response.status_code == 409, response.content
    body = response.json()
    assert body["code"] == "no_rate_available"
    assert net_plan.name in body["detail"]


@pytest.mark.django_db
def test_load_context_returns_none_on_multi_regime_stay(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateBand, net_plan: RatePlan
) -> None:
    assert (
        PricingEngine.load_context(
            property_, date_from=date(2026, 8, 30), date_to=date(2026, 9, 2), currency=gbp
        )
        is None
    )


@pytest.mark.django_db
def test_inactive_plan_and_inactive_period_do_not_make_a_second_regime(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateBand, net_plan: RatePlan
) -> None:
    net_plan.is_active = False
    net_plan.save(update_fields=["is_active"])
    plan.fallback_nightly = Decimal("50.00")
    plan.save(update_fields=["fallback_nightly"])

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 8, 30),
        date_to=date(2026, 9, 2),
        party=2,
        currency=gbp,
    )
    assert quote.rate_subtotal == Decimal("450.00")  # 200 + 200 + 50 fallback

    net_plan.is_active = True
    net_plan.save(update_fields=["is_active"])
    net_plan.periods.update(is_active=False)

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 8, 30),
        date_to=date(2026, 9, 2),
        party=2,
        currency=gbp,
    )
    assert quote.rate_subtotal == Decimal("450.00")


@pytest.mark.django_db
def test_other_currency_regimes_do_not_count(
    property_: Property, gbp: Currency, usd: Currency, plan: RatePlan, rule: RateBand
) -> None:
    """Two plans touching the stay in *different* currencies is the ordinary
    multi-currency villa, not a regime clash."""
    usd_plan = _plan(property_, usd)
    _priced_period(usd_plan, date(2026, 6, 1), date(2026, 8, 31), nightly="300.00")

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 13),
        party=2,
        currency=gbp,
    )
    assert quote.currency_code == "GBP"
    assert quote.rate_subtotal == Decimal("600.00")


# ---------------------------------------------------------------------------
# currency=None: which currency prices the stay
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_currency_covering_every_night_beats_a_partial_one(
    property_: Property, gbp: Currency, usd: Currency, plan: RatePlan
) -> None:
    """GBP has the lower plan pk *and* is the settings currency, but only covers
    part of the stay; USD covers all of it and wins."""
    _priced_period(plan, date(2026, 6, 1), date(2026, 6, 4))
    usd_plan = _plan(property_, usd)
    _priced_period(usd_plan, date(2026, 6, 1), date(2026, 6, 30), nightly="300.00")
    PropertySettings.objects.create(property=property_, currency=gbp)

    quote = PricingEngine.quote(
        property=property_, date_from=date(2026, 6, 1), date_to=date(2026, 6, 8), party=2
    )

    assert quote.currency_code == "USD"
    assert quote.rate_subtotal == Decimal("2100.00")


@pytest.mark.django_db
def test_two_full_coverage_currencies_prefer_the_settings_currency(
    property_: Property, gbp: Currency, usd: Currency, plan: RatePlan, rule: RateBand
) -> None:
    usd_plan = _plan(property_, usd)
    _priced_period(usd_plan, date(2026, 6, 1), date(2026, 8, 31), nightly="300.00")
    PropertySettings.objects.create(property=property_, currency=usd)

    quote = PricingEngine.quote(
        property=property_, date_from=date(2026, 6, 1), date_to=date(2026, 6, 8), party=2
    )

    assert quote.currency_code == "USD"


@pytest.mark.django_db
def test_two_full_coverage_currencies_without_settings_pick_the_lowest_plan_pk(
    property_: Property, gbp: Currency, usd: Currency, plan: RatePlan, rule: RateBand
) -> None:
    usd_plan = _plan(property_, usd)
    _priced_period(usd_plan, date(2026, 6, 1), date(2026, 8, 31), nightly="300.00")
    assert plan.pk < usd_plan.pk

    quote = PricingEngine.quote(
        property=property_, date_from=date(2026, 6, 1), date_to=date(2026, 6, 8), party=2
    )

    assert quote.currency_code == "GBP"


@pytest.mark.django_db
def test_no_full_coverage_currency_falls_back_to_settings_then_lowest_pk(
    property_: Property, gbp: Currency, usd: Currency, plan: RatePlan
) -> None:
    """Both currencies cover the same number of nights: settings currency
    decides; without settings, the lowest plan pk. (Each plan carries a
    fallback so the partly-covered stay prices and reveals its currency.)"""
    plan.fallback_nightly = Decimal("10.00")
    plan.save(update_fields=["fallback_nightly"])
    _priced_period(plan, date(2026, 6, 1), date(2026, 6, 3))
    usd_plan = _plan(property_, usd, fallback_nightly=Decimal("20.00"))
    _priced_period(usd_plan, date(2026, 6, 5), date(2026, 6, 7), nightly="300.00")

    def _quote_currency() -> str:
        return PricingEngine.quote(
            property=property_, date_from=date(2026, 6, 1), date_to=date(2026, 6, 8), party=2
        ).currency_code

    assert _quote_currency() == "GBP"

    PropertySettings.objects.create(property=property_, currency=usd)
    assert _quote_currency() == "USD"


@pytest.mark.django_db
def test_currency_covering_more_nights_wins_over_settings_and_pk(
    property_: Property, gbp: Currency, usd: Currency, plan: RatePlan
) -> None:
    """A stay straddling a currency switch prices in the currency that owns
    more of it — never on the *other* currency's fallback for nights the new
    currency has real rates for."""
    plan.fallback_nightly = Decimal("99.00")
    plan.save(update_fields=["fallback_nightly"])
    _priced_period(plan, date(2026, 6, 1), date(2026, 6, 30))  # GBP: 3 of the 7 nights
    usd_plan = _plan(property_, usd, fallback_nightly=Decimal("1.00"))
    _priced_period(usd_plan, date(2026, 7, 1), date(2026, 7, 31), nightly="300.00")  # 4 nights
    PropertySettings.objects.create(property=property_, currency=gbp)

    quote = PricingEngine.quote(
        property=property_, date_from=date(2026, 6, 28), date_to=date(2026, 7, 5), party=2
    )

    assert quote.currency_code == "USD"
    assert quote.rate_subtotal == Decimal("1203.00")  # 3 x 1 fallback + 4 x 300


@pytest.mark.django_db
def test_load_context_is_none_unless_the_periods_cover_every_night(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateBand
) -> None:
    """`load_context` hands back a context callers reuse for any sub-stay, so
    a range the periods only partly cover must not load — its uncovered
    sub-stays would price as fallback / no-rate instead of projecting."""
    plan.fallback_nightly = Decimal("99.00")
    plan.save(update_fields=["fallback_nightly"])

    assert (
        PricingEngine.load_context(
            property_, date_from=date(2026, 8, 28), date_to=date(2026, 9, 5), currency=gbp
        )
        is None
    )
    # The direct quote still prices the straddle with fallback for the gap.
    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 8, 28),
        date_to=date(2026, 9, 5),
        party=2,
        currency=gbp,
    )
    assert quote.rate_subtotal == Decimal("1196.00")  # 4 x 200 + 4 x 99


@pytest.mark.django_db
def test_regime_is_selected_on_the_changeover_shifted_nights(
    property_: Property, gbp: Currency, plan: RatePlan, rule: RateBand, net_plan: RatePlan
) -> None:
    """GROSS to 12 Jul, NET from 13 Jul, Saturday changeover: a Sun 12 → Sun 19
    request shifts to Sat 18 → Sat 25, entirely NET, and must price there —
    not raise `MultiRegimeStay` on the unshifted nights."""
    from properties.enums import PrefilledChangeOverDay
    from properties.models import ChangeOverRule

    ChangeOverRule.objects.create(
        property=property_,
        day=PrefilledChangeOverDay.SAT.value,
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 8, 31),
    )
    rule.period.date_to = date(2026, 7, 12)
    rule.period.save(update_fields=["date_to"])
    net_period = net_plan.periods.get()
    net_period.date_from = date(2026, 7, 13)
    net_period.save(update_fields=["date_from"])

    quote = PricingEngine.quote(
        property=property_,
        date_from=date(2026, 7, 12),
        date_to=date(2026, 7, 19),
        party=2,
        currency=gbp,
    )

    assert quote.breakdown["date_from"] == "2026-07-18"
    assert quote.rate_subtotal == Decimal("840.00")  # 7 x 120 NET


@pytest.mark.django_db
def test_plan_currency_drifted_from_its_periods_still_quotes(
    property_: Property, gbp: Currency, usd: Currency, plan: RatePlan, rule: RateBand
) -> None:
    """The regime pick is keyed by the periods' stamped currency, so a plan
    whose `currency` was changed behind `clean()`'s back (plain ORM save)
    degrades to a priced quote, never a KeyError."""
    usd_plan = _plan(property_, usd)
    _priced_period(usd_plan, date(2026, 6, 1), date(2026, 8, 31), nightly="300.00")
    eur = Currency.objects.create(code="EUR", name="Euro", symbol="€")
    plan.currency = eur
    plan.save(update_fields=["currency"])

    quote = PricingEngine.quote(
        property=property_, date_from=date(2026, 6, 10), date_to=date(2026, 6, 13), party=2
    )

    assert quote.rate_subtotal == Decimal("600.00")


@pytest.mark.django_db
def test_currency_choice_then_applies_the_single_currency_regime_rule(
    property_: Property,
    gbp: Currency,
    usd: Currency,
    plan: RatePlan,
    rule: RateBand,
    net_plan: RatePlan,
) -> None:
    """GBP wins the currency pick (full coverage via GROSS + NET together), and
    the two GBP regimes touching the stay then raise `MultiRegimeStay`."""
    usd_plan = _plan(property_, usd)
    _priced_period(usd_plan, date(2026, 8, 30), date(2026, 8, 31), nightly="300.00")

    with pytest.raises(MultiRegimeStay):
        PricingEngine.quote(
            property=property_, date_from=date(2026, 8, 30), date_to=date(2026, 9, 2), party=2
        )
