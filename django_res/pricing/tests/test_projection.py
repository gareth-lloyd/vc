"""Tests for lazy rate projection (date-map functions + RateProjectionService)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pricing.models import Currency, RateBand, RatePeriod, RatePlan
from pricing.services.projection import (
    RateProjectionService,
    keep_calendar_date,
    shift_to_changeover_weekday,
)
from properties.models import Property


def _period_of(rule: RateBand) -> RatePeriod:
    """The band's shim-derived period (never None once the rule is saved)."""
    period = rule.period
    assert period is not None
    return period


# --- date-map functions -----------------------------------------------------


def test_keep_calendar_date_relabels_year() -> None:
    assert keep_calendar_date(date(2026, 7, 4), 2) == date(2028, 7, 4)


def test_keep_calendar_date_handles_leap_day() -> None:
    # 29 Feb 2028 (leap) projected to 2029 (non-leap) clamps to 28 Feb.
    assert keep_calendar_date(date(2028, 2, 29), 1) == date(2029, 2, 28)


def test_shift_to_changeover_weekday_preserves_saturday() -> None:
    # 4 Jul 2026 is a Saturday; the nearest Saturday near 4 Jul 2028 (a Tuesday)
    # is 1 Jul 2028 — three days back, the minimal shift.
    source = date(2026, 7, 4)
    assert source.weekday() == 5  # Saturday
    mapped = shift_to_changeover_weekday(source, 2)
    assert mapped.weekday() == 5
    assert mapped == date(2028, 7, 1)


def test_shift_to_changeover_weekday_always_preserves_weekday_with_minimal_shift() -> None:
    # For any year delta the result keeps the source weekday and lands within
    # three days of the naive calendar date (the minimal nudge).
    source = date(2026, 6, 1)  # Monday
    for delta in range(1, 6):
        mapped = shift_to_changeover_weekday(source, delta)
        assert mapped.weekday() == source.weekday()
        assert abs((mapped - keep_calendar_date(source, delta)).days) <= 3


# --- anchor resolution ------------------------------------------------------


@pytest.fixture
def anchor_plan(property_: Property, gbp: Currency) -> RateBand:
    """A 2026 plan/period/rule to act as the projection anchor."""
    plan = RatePlan.objects.create(
        property=property_,
        name="Summer 2026",
        currency=gbp,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    period = RatePeriod.objects.create(
        plan=plan, name="Summer", date_from=date(2026, 6, 1), date_to=date(2026, 8, 31)
    )
    return RateBand.objects.create(
        period=period,
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )


@pytest.mark.django_db
def test_find_anchor_returns_most_recent_prior_plan(
    property_: Property, gbp: Currency, anchor_plan: RateBand
) -> None:
    newer = RatePlan.objects.create(
        property=property_,
        name="Summer 2027",
        currency=gbp,
        effective_from=date(2027, 1, 1),
        effective_to=date(2027, 12, 31),
    )
    found = RateProjectionService.find_anchor_plan(property_, gbp, date(2028, 7, 4))
    assert found == newer


@pytest.mark.django_db
def test_find_anchor_ignores_other_currency(
    property_: Property, gbp: Currency, usd: Currency, anchor_plan: RateBand
) -> None:
    found = RateProjectionService.find_anchor_plan(property_, usd, date(2028, 7, 4))
    assert found is None


@pytest.mark.django_db
def test_find_anchor_none_for_brand_new_villa(property_: Property, gbp: Currency) -> None:
    found = RateProjectionService.find_anchor_plan(property_, gbp, date(2028, 7, 4))
    assert found is None


@pytest.mark.django_db
def test_find_anchor_excludes_same_year_plan(
    property_: Property, gbp: Currency, anchor_plan: RateBand
) -> None:
    # A plan whose effective_from is in the target year is not an anchor for that
    # year — it would anchor on itself.
    RatePlan.objects.create(
        property=property_,
        name="Partial 2028",
        currency=gbp,
        effective_from=date(2028, 1, 1),
        effective_to=date(2028, 3, 31),
    )
    found = RateProjectionService.find_anchor_plan(property_, gbp, date(2028, 7, 4))
    assert found is not None
    assert found.name == "Summer 2026"


# --- project() --------------------------------------------------------------


@pytest.mark.django_db
def test_project_builds_shifted_in_memory_context(
    property_: Property, gbp: Currency, anchor_plan: RateBand
) -> None:
    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(2028, 7, 4),
        currency=gbp,
        date_map=keep_calendar_date,
    )
    assert ctx is not None
    assert ctx.is_projected is True
    # Synthesized plan / card / rule reference the real source rows (free
    # traceability) but were never saved — only one plan exists in the DB.
    assert ctx.plan.pk == anchor_plan.period.plan.pk
    assert RatePlan.objects.count() == 1
    # Bands inherit the period's (shifted) dates — the projected period carries them.
    [period] = ctx.periods
    assert period.date_from == date(2028, 6, 1)
    assert period.date_to == date(2028, 8, 31)
    [rule] = ctx.bands_by_period[_period_of(anchor_plan).pk]
    assert rule.pk == anchor_plan.pk
    assert rule.nightly == Decimal("200.00")
    assert ctx.projection == {
        "source_plan_id": anchor_plan.period.plan.pk,
        "source_year": 2026,
        "target_year": 2028,
        "uplift_pct": "0.00",
        "date_map": "keep_calendar_date",
    }


@pytest.mark.django_db
def test_project_applies_uplift(property_: Property, gbp: Currency, anchor_plan: RateBand) -> None:
    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(2028, 7, 4),
        currency=gbp,
        date_map=keep_calendar_date,
        uplift=Decimal("0.05"),
    )
    assert ctx is not None
    assert ctx.projection is not None
    [rule] = ctx.bands_by_period[_period_of(anchor_plan).pk]
    assert rule.nightly == Decimal("210.00")
    assert ctx.projection["uplift_pct"] == "5.00"


@pytest.mark.django_db
def test_project_preserves_poa(property_: Property, gbp: Currency, anchor_plan: RateBand) -> None:
    poa = anchor_plan
    poa.nightly = None
    poa.is_poa = True
    poa.save(update_fields=["nightly", "is_poa"])
    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(2028, 7, 4),
        currency=gbp,
    )
    assert ctx is not None
    [rule] = ctx.bands_by_period[_period_of(poa).pk]
    assert rule.is_poa is True
    assert rule.nightly is None


@pytest.mark.django_db
def test_project_skips_unapproved_rules(
    property_: Property, gbp: Currency, anchor_plan: RateBand
) -> None:
    extra_period = RatePeriod.objects.create(
        plan=anchor_plan.period.plan,
        name="September",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
    )
    RateBand.objects.create(
        period=extra_period,
        min_party=1,
        max_party=8,
        nightly=Decimal("300.00"),
        is_approved=False,
    )
    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(2028, 7, 4),
        currency=gbp,
    )
    assert ctx is not None
    # Only the approved source rule seeds the projection.
    assert len(ctx.bands_by_period[_period_of(anchor_plan).pk]) == 1


@pytest.mark.django_db
def test_project_none_without_anchor(property_: Property, gbp: Currency) -> None:
    assert (
        RateProjectionService.project(
            property=property_,
            date_from=date(2028, 7, 4),
            currency=gbp,
        )
        is None
    )


# --- BUG-016 period-id rule -------------------------------------------------


def _collision_anchor(
    property_: Property, gbp: Currency, late_feb_bracket: tuple[int, int]
) -> tuple[RatePeriod, RatePeriod]:
    """Anchor whose Feb-29 span collides with its neighbour after mapping."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
    )
    late_feb = RatePeriod.objects.create(
        plan=plan, name="Late Feb", date_from=date(2024, 2, 25), date_to=date(2024, 2, 29)
    )
    RateBand.objects.create(
        period=late_feb,
        min_party=late_feb_bracket[0],
        max_party=late_feb_bracket[1],
        nightly=Decimal("100.00"),
    )
    early_march = RatePeriod.objects.create(
        plan=plan, name="Early March", date_from=date(2024, 3, 1), date_to=date(2024, 3, 7)
    )
    RateBand.objects.create(period=early_march, min_party=1, max_party=8, nightly=Decimal("150.00"))
    return late_feb, early_march


@pytest.mark.django_db
def test_project_single_parentage_periods_keep_source_pks(
    property_: Property, gbp: Currency
) -> None:
    """A clean carry (collision fully shadows the loser's contested day) keeps
    every projected period on its source pk — full traceability."""
    late_feb, early_march = _collision_anchor(property_, gbp, late_feb_bracket=(1, 8))
    ctx = RateProjectionService.project(
        property=property_, date_from=date(2025, 2, 1), currency=gbp, date_map=keep_calendar_date
    )
    assert ctx is not None
    # Late Feb absorbs the contested 1 Mar (same bracket, lower pk); Early
    # March survives as one fragment. Both are single-parentage, pks free.
    assert [(p.pk, p.date_from, p.date_to) for p in ctx.periods] == [
        (late_feb.pk, date(2025, 2, 25), date(2025, 3, 1)),
        (early_march.pk, date(2025, 3, 2), date(2025, 3, 7)),
    ]


@pytest.mark.django_db
def test_project_mixed_parentage_period_gets_negative_synthetic_id(
    property_: Property, gbp: Currency
) -> None:
    """The contested day regroups bands from two source periods: no single
    parent pk to keep, so it gets a deterministic negative id. Band ids stay
    the source rule pks throughout."""
    late_feb, early_march = _collision_anchor(property_, gbp, late_feb_bracket=(1, 4))
    ctx = RateProjectionService.project(
        property=property_, date_from=date(2025, 2, 1), currency=gbp, date_map=keep_calendar_date
    )
    assert ctx is not None
    assert [(p.pk, p.date_from, p.date_to) for p in ctx.periods] == [
        (late_feb.pk, date(2025, 2, 25), date(2025, 2, 28)),
        (-1, date(2025, 3, 1), date(2025, 3, 1)),
        (early_march.pk, date(2025, 3, 2), date(2025, 3, 7)),
    ]
    # bands_by_period is keyed on the synthetic id; band ids = source rule pks.
    mixed = ctx.bands_by_period[-1]
    assert {band.pk for band in mixed} == set(
        RateBand.objects.filter(period__plan=late_feb.plan).values_list("pk", flat=True)
    )


@pytest.mark.django_db
def test_project_second_fragment_of_reused_parent_gets_negative_id(
    property_: Property, gbp: Currency
) -> None:
    """When the weekday map lands a band on both sides of an earlier claim,
    its two fragments share one source period — only the first (date order)
    keeps the pk."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
        effective_from=date(2024, 1, 1),
        effective_to=date(2024, 12, 31),
    )
    late_feb = RatePeriod.objects.create(
        plan=plan, name="Late Feb", date_from=date(2024, 2, 26), date_to=date(2024, 2, 29)
    )
    RateBand.objects.create(period=late_feb, min_party=1, max_party=8, nightly=Decimal("100.00"))
    early_march = RatePeriod.objects.create(
        plan=plan, name="Early March", date_from=date(2024, 3, 1), date_to=date(2024, 3, 10)
    )
    RateBand.objects.create(period=early_march, min_party=1, max_party=8, nightly=Decimal("150.00"))
    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(2027, 2, 1),
        currency=gbp,
        date_map=shift_to_changeover_weekday,
    )
    assert ctx is not None
    # Early March maps to [26 Feb - 7 Mar], Late Feb claims [1 - 4 Mar]:
    # Early March's leading fragment keeps its pk, the trailing one gets -1.
    assert [(p.pk, p.date_from, p.date_to) for p in ctx.periods] == [
        (early_march.pk, date(2027, 2, 26), date(2027, 2, 28)),
        (late_feb.pk, date(2027, 3, 1), date(2027, 3, 4)),
        (-1, date(2027, 3, 5), date(2027, 3, 7)),
    ]


@pytest.mark.django_db
def test_project_keeps_fallback_only_context_when_no_approved_bands(
    property_: Property, gbp: Currency, anchor_plan: RateBand
) -> None:
    """An anchor whose active periods carry no approved bands still projects:
    the engine prices such a context at the plan's fallback_nightly, exactly
    like the real-plan shape it mirrors. Returning None here would flip a
    priced guide quote into NoRateAvailable."""
    plan = anchor_plan.period.plan
    plan.fallback_nightly = Decimal("120.00")
    plan.save(update_fields=["fallback_nightly"])
    anchor_plan.is_approved = False
    anchor_plan.save(update_fields=["is_approved"])

    ctx = RateProjectionService.project(
        property=property_, date_from=date(2028, 7, 4), currency=gbp
    )
    assert ctx is not None
    assert ctx.periods == []
    assert ctx.bands_by_period == {}
    assert ctx.plan.fallback_nightly == Decimal("120.00")
