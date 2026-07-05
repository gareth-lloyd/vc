"""BUG-016 acceptance — a projected quote equals its materialised twin.

`RateProjectionService.project` (in-memory guide rate) and
`RateCarryoverService.materialise` (persisted rows for the same year) both
consume `flatten_rate_grid`, so the grids they produce must be byte-identical
(period spans, names, min/max nights, band brackets, prices, POA) and price
every (night, party) point identically. Cases cover the ticket's tie-break,
collision, and Feb-29/boundary axes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import pytest

from pricing.models import Currency, RateBand, RatePeriod, RatePlan
from pricing.services.carryover import RateCarryoverService
from pricing.services.projection import (
    DateMap,
    PricingContext,
    RateProjectionService,
    keep_calendar_date,
    shift_to_changeover_weekday,
)
from pricing.services.rates import Picked, pick_band_for_night
from properties.models import Property

# (min_party, max_party, nightly, is_poa)
BandSpec = tuple[int, int, Decimal | None, bool]


@dataclass(frozen=True)
class PeriodSpec:
    name: str
    date_from: date
    date_to: date
    bands: list[BandSpec]
    min_nights: int | None = None
    max_nights: int | None = None


@dataclass(frozen=True)
class Case:
    """An anchor-year grid plus the projection knobs to carry it forward."""

    periods: list[PeriodSpec]
    date_map: DateMap = keep_calendar_date
    target_year: int = 2025
    uplift: Decimal = field(default=Decimal("0"))


N100 = Decimal("100.00")
N150 = Decimal("150.00")

CASES = {
    # Two clean periods — names and nights must round-trip untouched.
    "plain_no_collision": Case(
        periods=[
            PeriodSpec("June", date(2024, 6, 1), date(2024, 6, 30), [(1, 8, N100, False)], 7),
            PeriodSpec("July", date(2024, 7, 1), date(2024, 7, 31), [(1, 8, N150, False)], 7, 14),
        ],
    ),
    # pk order opposes date order; the Feb-29 span lands on its neighbour.
    "tie_break_feb29": Case(
        periods=[
            PeriodSpec("March week", date(2024, 3, 1), date(2024, 3, 7), [(1, 8, N150, False)]),
            PeriodSpec("Late Feb", date(2024, 2, 25), date(2024, 2, 29), [(1, 8, N100, False)]),
        ],
    ),
    # Weekday map shifts neighbours toward each other (±3 at delta 3): the
    # later band keeps remainders on BOTH sides of the earlier band's claim.
    "weekday_double_shift": Case(
        periods=[
            PeriodSpec("Late Feb", date(2024, 2, 26), date(2024, 2, 29), [(1, 8, N100, False)]),
            PeriodSpec("Early March", date(2024, 3, 1), date(2024, 3, 10), [(1, 8, N150, False)]),
        ],
        date_map=shift_to_changeover_weekday,
        target_year=2027,
    ),
    # The collision trims the later band to a single surviving day.
    "single_day_sliver": Case(
        periods=[
            PeriodSpec("Late Feb", date(2024, 2, 27), date(2024, 2, 29), [(1, 8, N100, False)]),
            PeriodSpec("Early March", date(2024, 3, 1), date(2024, 3, 2), [(1, 8, N150, False)]),
        ],
    ),
    # The BUG-016 money case: narrow lower-pk winner, wide higher-pk loser —
    # the loser's party 5-8 must survive on the contested day in BOTH paths.
    "party_widening": Case(
        periods=[
            PeriodSpec("Late Feb", date(2024, 2, 25), date(2024, 2, 29), [(1, 4, N100, False)]),
            PeriodSpec("Early March", date(2024, 3, 1), date(2024, 3, 7), [(1, 8, N150, False)]),
        ],
    ),
    # A POA band in the collision — the flag must survive fragmenting.
    "poa_in_collision": Case(
        periods=[
            PeriodSpec("Late Feb", date(2024, 2, 25), date(2024, 2, 29), [(1, 8, None, True)]),
            PeriodSpec("Early March", date(2024, 3, 1), date(2024, 3, 7), [(1, 8, N150, False)]),
        ],
    ),
    # Party-disjoint parents share the contested day: the flat period takes the
    # WINNER's (lowest source pk) min/max nights in both paths — the lazy
    # projection used to validate against the picked band's own source period.
    "min_nights_on_collision": Case(
        periods=[
            PeriodSpec("Late Feb", date(2024, 2, 25), date(2024, 2, 29), [(1, 4, N100, False)], 7),
            PeriodSpec("Early March", date(2024, 3, 1), date(2024, 3, 7), [(5, 8, N150, False)], 3),
        ],
    ),
    # No approved bands at all: both paths yield an EMPTY grid and price via
    # the plan's fallback_nightly — neither may fail with NoRateAvailable.
    "fallback_only_no_approved_bands": Case(
        periods=[
            PeriodSpec("Draft June", date(2024, 6, 1), date(2024, 6, 30), []),
        ],
    ),
    # Uplift composes with collision resolution identically in both paths.
    "uplift_with_collision": Case(
        periods=[
            PeriodSpec("Late Feb", date(2024, 2, 25), date(2024, 2, 29), [(1, 8, N100, False)]),
            PeriodSpec("Early March", date(2024, 3, 1), date(2024, 3, 7), [(1, 8, N150, False)]),
        ],
        uplift=Decimal("0.10"),
    ),
}


def _build_anchor(property_: Property, gbp: Currency, case: Case) -> RatePlan:
    plan = RatePlan.objects.create(
        property=property_,
        name="Anchor 2024",
        currency=gbp,
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
        fallback_nightly=Decimal("80.00"),
    )
    for spec in case.periods:
        period = RatePeriod.objects.create(
            plan=plan,
            name=spec.name,
            date_from=spec.date_from,
            date_to=spec.date_to,
            min_nights=spec.min_nights,
            max_nights=spec.max_nights,
        )
        for min_party, max_party, nightly, is_poa in spec.bands:
            RateBand.objects.create(
                period=period,
                min_party=min_party,
                max_party=max_party,
                nightly=nightly,
                is_poa=is_poa,
            )
        if not spec.bands:
            # A draft (unapproved) band: the period exists but nothing on it
            # may price — the fallback-only shape.
            RateBand.objects.create(
                period=period, min_party=1, max_party=8, nightly=N100, is_approved=False
            )
    return plan


Snapshot = list[tuple]


def _row(period: RatePeriod, bands: list[RateBand]) -> tuple:
    return (
        period.date_from,
        period.date_to,
        period.name,
        period.min_nights,
        period.max_nights,
        [(b.min_party, b.max_party, b.nightly, b.weekly, b.is_poa) for b in bands],
    )


def _projected_snapshot(ctx: PricingContext) -> Snapshot:
    return [
        _row(period, sorted(ctx.bands_by_period.get(period.pk, []), key=lambda b: b.min_party))
        for period in sorted(ctx.periods, key=lambda p: p.date_from)
    ]


def _materialised_snapshot(plan: RatePlan) -> Snapshot:
    return [
        _row(period, list(period.bands.order_by("min_party")))
        for period in RatePeriod.objects.filter(plan=plan).order_by("date_from")
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(CASES))
def test_projected_grid_is_byte_identical_to_materialised_twin(
    name: str, property_: Property, gbp: Currency
) -> None:
    case = CASES[name]
    _build_anchor(property_, gbp, case)

    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(case.target_year, 2, 1),
        currency=gbp,
        date_map=case.date_map,
        uplift=case.uplift,
    )
    assert ctx is not None
    plan = RateCarryoverService.materialise(
        property_,
        target_year=case.target_year,
        currency=gbp,
        date_map=case.date_map,
        uplift=case.uplift,
    )

    assert _projected_snapshot(ctx) == _materialised_snapshot(plan)
    # The plan-level pricing inputs must agree too (fallback pricing when the
    # grid is empty; basis drives gross/net maths).
    assert ctx.plan.fallback_nightly == plan.fallback_nightly
    assert ctx.plan.price_basis == plan.price_basis


@pytest.mark.django_db
@pytest.mark.parametrize("name", sorted(CASES))
def test_projected_quote_prices_every_point_like_materialised_twin(
    name: str, property_: Property, gbp: Currency
) -> None:
    case = CASES[name]
    _build_anchor(property_, gbp, case)

    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(case.target_year, 2, 1),
        currency=gbp,
        date_map=case.date_map,
        uplift=case.uplift,
    )
    assert ctx is not None
    plan = RateCarryoverService.materialise(
        property_,
        target_year=case.target_year,
        currency=gbp,
        date_map=case.date_map,
        uplift=case.uplift,
    )
    mat_periods = list(RatePeriod.objects.filter(plan=plan, is_active=True))
    mat_rules = {p.pk: list(p.bands.all()) for p in mat_periods}

    if not mat_periods:
        # Fallback-only shape: nothing to walk — equivalence is the empty
        # grid on both sides (pinned by the byte-identical test).
        assert ctx.periods == []
        return

    lo = min(p.date_from for p in mat_periods) - timedelta(days=1)
    hi = max(p.date_to for p in mat_periods) + timedelta(days=1)
    night = lo
    while night <= hi:
        for party in range(1, 11):
            projected = pick_band_for_night(ctx.periods, ctx.bands_by_period, night, party)
            materialised = pick_band_for_night(mat_periods, mat_rules, night, party)
            point = f"{name} night={night} party={party}"
            assert type(projected) is type(materialised), point
            if isinstance(projected, Picked):
                assert isinstance(materialised, Picked)
                proj_rule, mat_rule = projected.rule, materialised.rule
                assert (
                    proj_rule.min_party,
                    proj_rule.max_party,
                    proj_rule.nightly,
                    proj_rule.weekly,
                    proj_rule.is_poa,
                ) == (
                    mat_rule.min_party,
                    mat_rule.max_party,
                    mat_rule.nightly,
                    mat_rule.weekly,
                    mat_rule.is_poa,
                ), point
                # The stay-length rules the engine validates with must agree
                # too — min/max nights live on the picked period.
                assert (
                    projected.period.date_from,
                    projected.period.date_to,
                    projected.period.name,
                    projected.period.min_nights,
                    projected.period.max_nights,
                ) == (
                    materialised.period.date_from,
                    materialised.period.date_to,
                    materialised.period.name,
                    materialised.period.min_nights,
                    materialised.period.max_nights,
                ), point
        night += timedelta(days=1)
