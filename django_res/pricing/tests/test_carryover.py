"""Tests for RateCarryoverService.materialise (the on-demand promote action)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from core.exceptions import NoRateAvailable, RegimeConflict
from pricing.models import Currency, RateBand, RatePeriod, RatePlan
from pricing.services.carryover import RateCarryoverService
from pricing.services.period_names import derive_period_name
from pricing.services.projection import (
    RateProjectionService,
    keep_calendar_date,
    shift_to_changeover_weekday,
)
from pricing.services.rates import Picked, nights, pick_band_for_night, rule_nightly
from properties.models import Property


@pytest.fixture
def anchor_rule(property_: Property, gbp: Currency) -> RateBand:
    """A 2026 plan/period/rule to carry forward."""
    plan = RatePlan.objects.create(
        property=property_,
        name="Summer 2026",
        currency=gbp,
        fallback_nightly=Decimal("120.00"),
    )
    # min-nights lives on the period now (GAP-056); "Peak" is the period label.
    period = RatePeriod.objects.create(
        plan=plan,
        name="Peak",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_nights=7,
    )
    return RateBand.objects.create(
        period=period,
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )


@pytest.mark.django_db
def test_materialise_writes_real_rows_for_target_year(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    new_plan = RateCarryoverService.materialise(
        property_,
        target_year=2028,
        currency=gbp,
        date_map=keep_calendar_date,
    )

    # GAP-110: the regime plan is the date-less bucket — carried periods land
    # on it; no new plan is minted.
    assert new_plan.pk == anchor_rule.period.plan.pk
    assert RatePlan.objects.filter(property=property_, currency=gbp).count() == 1

    period = new_plan.periods.get(date_from__year=2028)
    # The period carries the anchor period's dates (mapped) + min-nights.
    assert period.min_nights == 7
    assert period.date_from == date(2028, 6, 1)
    assert period.date_to == date(2028, 8, 31)
    rule = period.bands.get()
    assert rule.nightly == Decimal("200.00")
    # A distinct, editable row — not the anchor.
    assert rule.pk != anchor_rule.pk
    assert rule.is_locked is False


@pytest.mark.django_db
def test_materialise_is_idempotent(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    first = RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)
    second = RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)

    assert first.pk == second.pk
    # One 2028 period — a re-run never duplicates (the anchor's own 2026
    # period is the only other row).
    assert RatePeriod.objects.filter(plan=first, date_from__year=2028).count() == 1
    assert RateBand.objects.filter(period__plan=first).count() == 2


@pytest.mark.django_db
def test_materialise_is_idempotent_across_active_plans_in_the_regime(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """A target-year period on *any* active plan of the (property, currency)
    regime — a NET plan alongside the GROSS anchor — already prices that
    year, so the carry is a no-op returning that plan."""
    net_plan = RatePlan.objects.create(
        property=property_,
        name="Net rates",
        currency=gbp,
        price_basis="net",
    )
    RatePeriod.objects.create(
        plan=net_plan, name="Spring 2028", date_from=date(2028, 3, 1), date_to=date(2028, 3, 31)
    )
    returned = RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)
    assert returned == net_plan
    assert not RatePeriod.objects.filter(plan=anchor_rule.period.plan, date_from__year=2028)


@pytest.mark.django_db
def test_materialise_refuses_a_target_year_owned_by_withdrawn_rows(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """A retired sibling plan's period (or a withdrawn period on the anchor
    plan itself) still owns its dates in the regime-wide EXCLUDE; carrying
    into that year would land nothing on those dates, so it is refused with
    guidance rather than reported as a success."""
    retired = RatePlan.objects.create(
        property=property_,
        name="Retired",
        currency=gbp,
        is_active=False,
    )
    RatePeriod.objects.create(
        plan=retired, name="Owned", date_from=date(2028, 6, 15), date_to=date(2028, 7, 15)
    )
    with pytest.raises(RegimeConflict, match='"Owned" on plan "Retired"'):
        RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)
    assert not anchor_rule.period.plan.periods.filter(date_from__year=2028).exists()

    RatePeriod.objects.filter(plan=retired).delete()
    RatePeriod.objects.create(
        plan=anchor_rule.period.plan,
        name="Withdrawn",
        date_from=date(2028, 3, 1),
        date_to=date(2028, 3, 31),
        is_active=False,
    )
    with pytest.raises(RegimeConflict, match='"Withdrawn"'):
        RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)


@pytest.mark.django_db
def test_materialise_clips_around_the_next_years_rows(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """A December tail mapped into a year whose successor is already carried
    is clipped where the successor's January period starts."""
    plan = anchor_rule.period.plan
    tail = RatePeriod.objects.create(
        plan=plan, name="Festive", date_from=date(2027, 12, 27), date_to=date(2028, 1, 3)
    )
    RateBand.objects.create(period=tail, min_party=1, max_party=8, nightly=Decimal("400.00"))
    RatePeriod.objects.create(
        plan=plan, name="New Year 2029", date_from=date(2029, 1, 1), date_to=date(2029, 1, 7)
    )

    RateCarryoverService.materialise(
        property_, target_year=2028, currency=gbp, date_map=keep_calendar_date
    )
    carried = plan.periods.filter(date_from__year=2028).order_by("date_from")
    assert [(p.date_from, p.date_to, p.name) for p in carried] == [
        (date(2028, 12, 27), date(2028, 12, 31), "Festive"),
    ]
    assert carried.get().bands.get().nightly == Decimal("400.00")


@pytest.mark.django_db
def test_materialise_keeps_a_new_year_period_in_its_year_under_the_weekday_map(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """A period belongs to the year its `date_from` falls in, so the default
    weekday map must not nudge 1 Jan back into December — the row would then
    be invisible to the next carry's anchor set and to the idempotency check."""
    plan = anchor_rule.period.plan
    new_year = RatePeriod.objects.create(
        plan=plan, name="New Year", date_from=date(2027, 1, 1), date_to=date(2027, 1, 7)
    )
    RateBand.objects.create(period=new_year, min_party=1, max_party=8, nightly=Decimal("350.00"))

    # 1 Jan 2027 is a Friday; the naive 1 Jan 2028 is a Saturday, so the
    # weekday map alone would land on 31 Dec 2027.
    RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)
    carried = plan.periods.filter(date_from__year=2028).order_by("date_from")
    assert [(p.date_from, p.date_to) for p in carried] == [(date(2028, 1, 1), date(2028, 1, 7))]
    # ...and the next carry sees it as 2028's New Year.
    RateCarryoverService.materialise(property_, target_year=2029, currency=gbp)
    assert plan.periods.filter(date_from__year=2029, name="New Year").exists()


@pytest.mark.django_db
def test_next_target_year_follows_the_latest_live_period(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    plan = anchor_rule.period.plan
    assert RateCarryoverService.next_target_year(property_, gbp) == 2027
    RatePeriod.objects.create(
        plan=plan,
        name="Withdrawn 2029",
        date_from=date(2029, 6, 1),
        date_to=date(2029, 8, 31),
        is_active=False,
    )
    assert RateCarryoverService.next_target_year(property_, gbp) == 2027
    plan.is_active = False
    plan.save(update_fields=["is_active"])
    assert RateCarryoverService.next_target_year(property_, gbp) is None


@pytest.mark.django_db
def test_materialise_clips_a_straddling_new_year_tail(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """A 2027 New-Year period mapped into 2028 collides with the 2027 tail that
    crosses into January 2028; the overlap is clipped, not refused."""
    plan = anchor_rule.period.plan
    tail = RatePeriod.objects.create(
        plan=plan, name="Festive", date_from=date(2027, 12, 27), date_to=date(2028, 1, 3)
    )
    RateBand.objects.create(period=tail, min_party=1, max_party=8, nightly=Decimal("400.00"))
    new_year = RatePeriod.objects.create(
        plan=plan, name="New Year", date_from=date(2027, 1, 1), date_to=date(2027, 1, 7)
    )
    RateBand.objects.create(period=new_year, min_party=1, max_party=8, nightly=Decimal("350.00"))

    RateCarryoverService.materialise(
        property_, target_year=2028, currency=gbp, date_map=keep_calendar_date
    )
    carried = plan.periods.filter(date_from__year=2028).order_by("date_from")
    assert [(p.date_from, p.date_to, p.name) for p in carried] == [
        (date(2028, 1, 4), date(2028, 1, 7), "New Year"),
        (date(2028, 12, 27), date(2029, 1, 3), "Festive"),
    ]


@pytest.mark.django_db
def test_materialise_applies_uplift(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    new_plan = RateCarryoverService.materialise(
        property_,
        target_year=2028,
        currency=gbp,
        uplift=Decimal("0.10"),
    )
    rule = RateBand.objects.get(period__plan=new_plan, period__date_from__year=2028)
    assert rule.nightly == Decimal("220.00")


@pytest.mark.django_db
def test_materialise_skips_inactive_periods_and_unapproved_rules(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """The carried set matches the guide a quote would show — no dormant rows."""
    anchor_plan = anchor_rule.period.plan
    # An inactive period (disjoint dates — periods can't share a span) whose band
    # must not be carried.
    inactive = RatePeriod.objects.create(
        plan=anchor_plan,
        name="Inactive Sept",
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
        is_active=False,
    )
    RateBand.objects.create(
        period=inactive,
        min_party=1,
        max_party=8,
        nightly=Decimal("999.00"),
    )
    # An unapproved band on a separate active period — filtered by is_approved.
    unapproved_period = RatePeriod.objects.create(
        plan=anchor_plan, name="October", date_from=date(2026, 10, 1), date_to=date(2026, 10, 31)
    )
    RateBand.objects.create(
        period=unapproved_period,
        min_party=1,
        max_party=8,
        nightly=Decimal("888.00"),
        is_approved=False,
    )

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2028, currency=gbp, date_map=keep_calendar_date
    )

    # Only the active period's approved rule is carried forward.
    assert new_plan.periods.filter(date_from__year=2028).count() == 1
    assert new_plan.periods.get(date_from__year=2028).min_nights == 7  # the carried anchor period
    assert RateBand.objects.filter(period__plan=new_plan, period__date_from__year=2028).count() == 1


@pytest.mark.django_db
def test_materialise_without_anchor_raises(property_: Property, gbp: Currency) -> None:
    with pytest.raises(NoRateAvailable):
        RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)


@pytest.mark.django_db
def test_materialise_clips_date_map_collisions(property_: Property, gbp: Currency) -> None:
    """A leap-year anchor range spanning Feb 29 lands one day longer relative
    to its neighbour after mapping (span is preserved, Feb 29 isn't), so the
    shifted ranges collide on the boundary. materialise must clip the later
    rule instead of tripping raterule_no_overlap with an IntegrityError."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
    )
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan,
            name="Late Feb",
            date_from=date(2024, 2, 25),
            date_to=date(2024, 2, 29),  # spans Feb 29
        ),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan, name="Early March", date_from=date(2024, 3, 1), date_to=date(2024, 3, 7)
        ),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2025, currency=gbp, date_map=keep_calendar_date
    )

    new_rules = list(
        RateBand.objects.filter(period__plan=new_plan, period__date_from__year=2025).order_by(
            "period__date_from"
        ),
    )
    assert [(r.period.date_from, r.period.date_to) for r in new_rules] == [
        (date(2025, 2, 25), date(2025, 3, 1)),  # span preserved across the lost Feb 29
        (date(2025, 3, 2), date(2025, 3, 7)),  # clipped off the collided boundary day
    ]


@pytest.mark.django_db
def test_materialise_splits_around_earlier_rule(property_: Property, gbp: Currency) -> None:
    """The weekday map can shift neighbours in opposite directions across a
    leap boundary (here ±3 days at year_delta=3), so a later rule's mapped
    range can extend on *both* sides of an earlier rule's claim. The free
    leading segment must survive as its own row — not be discarded by a
    forward-only clip."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
    )
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan,
            name="Late Feb",
            date_from=date(2024, 2, 26),  # Mon → maps +3 to Mon 1 Mar 2027
            date_to=date(2024, 2, 29),
        ),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan,
            name="Early March",
            date_from=date(2024, 3, 1),  # Fri → maps -3 to Fri 26 Feb 2027
            date_to=date(2024, 3, 10),
        ),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2027, currency=gbp, date_map=shift_to_changeover_weekday
    )

    new_rules = list(
        RateBand.objects.filter(period__plan=new_plan, period__date_from__year=2027).order_by(
            "period__date_from"
        )
    )
    # Rule A claims [1 Mar - 4 Mar]; rule B ([26 Feb - 7 Mar] mapped) keeps
    # both remainders around it.
    assert [(r.period.date_from, r.period.date_to, r.nightly) for r in new_rules] == [
        (date(2027, 2, 26), date(2027, 2, 28), Decimal("150.00")),
        (date(2027, 3, 1), date(2027, 3, 4), Decimal("100.00")),
        (date(2027, 3, 5), date(2027, 3, 7), Decimal("150.00")),
    ]


@pytest.mark.django_db
def test_materialise_persists_single_day_sliver(property_: Property, gbp: Currency) -> None:
    """A collision that trims a later rule down to a single-day remainder must
    still persist that day — inclusive periods (GAP-056) make `date_from ==
    date_to` a legitimate row, so materialise no longer silently drops it
    (which would leave the projection's price for that night unmatched)."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
    )
    # Lower pk, spans Feb 29: maps (keep_calendar, +1yr) to [27 Feb - 1 Mar] 2025
    # (span preserved across the lost leap day), claiming 1 Mar first.
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan, name="Late Feb", date_from=date(2024, 2, 27), date_to=date(2024, 2, 29)
        ),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )
    # Higher pk, [1 Mar - 2 Mar] 2024 → maps to the same dates 2025; 1 Mar is
    # claimed above, leaving a single-day remainder on 2 Mar.
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan, name="Early March", date_from=date(2024, 3, 1), date_to=date(2024, 3, 2)
        ),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2025, currency=gbp, date_map=keep_calendar_date
    )

    new_rules = list(
        RateBand.objects.filter(period__plan=new_plan, period__date_from__year=2025).order_by(
            "period__date_from"
        )
    )
    assert [(r.period.date_from, r.period.date_to, r.nightly) for r in new_rules] == [
        (date(2025, 2, 27), date(2025, 3, 1), Decimal("100.00")),
        (date(2025, 3, 2), date(2025, 3, 2), Decimal("150.00")),  # single-day sliver survives
    ]
    # The sliver is carried on a native single-day period (date_from == date_to),
    # not left orphaned — every carried band has a period parent.
    sliver = new_rules[1]
    assert sliver.period is not None
    assert sliver.period.date_from == date(2025, 3, 2)
    assert sliver.period.date_to == date(2025, 3, 2)


@pytest.mark.django_db
def test_materialise_keeps_wider_party_remainder_on_collision(
    property_: Property, gbp: Currency
) -> None:
    """BUG-016: when a lower-pk narrow band (party 1-4) claims a collided day,
    the wider higher-pk band (party 1-8) must keep serving party 5-8 on that
    day — the projection prices it, so the materialised twin must too. The old
    claim loop gated on party overlap but subtracted only dates, silently
    widening the winner's party claim to the loser's whole bracket."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
    )
    # Lower pk, party 1-4, spans Feb 29: maps to [25 Feb - 1 Mar] 2025.
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan, name="Late Feb", date_from=date(2024, 2, 25), date_to=date(2024, 2, 29)
        ),
        min_party=1,
        max_party=4,
        nightly=Decimal("100.00"),
    )
    # Higher pk, party 1-8, [1 Mar - 7 Mar] -> same dates 2025; collides on 1 Mar.
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan, name="Early March", date_from=date(2024, 3, 1), date_to=date(2024, 3, 7)
        ),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )

    ctx = RateProjectionService.project(
        property=property_, date_from=date(2025, 2, 1), currency=gbp, date_map=keep_calendar_date
    )
    assert ctx is not None
    new_plan = RateCarryoverService.materialise(
        property_, target_year=2025, currency=gbp, date_map=keep_calendar_date
    )

    # The contested day keeps a party-5-8 fragment of the wider band.
    collided = RatePeriod.objects.get(plan=new_plan, date_from=date(2025, 3, 1))
    assert collided.date_to == date(2025, 3, 1)
    assert sorted(
        collided.bands.values_list("min_party", "max_party", "nightly"),
    ) == [(1, 4, Decimal("100.00")), (5, 8, Decimal("150.00"))]

    # And a party-6 guest on that night prices identically in both paths.
    mat_periods = list(
        RatePeriod.objects.filter(plan=new_plan, is_active=True, date_from__year=2025)
    )
    mat_rules = {p.pk: list(p.bands.all()) for p in mat_periods}
    projected = pick_band_for_night(ctx.periods, ctx.bands_by_period, date(2025, 3, 1), party=6)
    materialised = pick_band_for_night(mat_periods, mat_rules, date(2025, 3, 1), party=6)
    assert isinstance(projected, Picked)
    assert isinstance(materialised, Picked)
    assert rule_nightly(materialised.rule) == rule_nightly(projected.rule) == Decimal("150.00")


@pytest.mark.django_db
def test_materialise_matches_projection_night_by_night(property_: Property, gbp: Currency) -> None:
    """materialise's contract: the rows it writes price every night exactly as
    the in-memory projection would have. Collisions resolve to the lowest
    source pk in both paths — even when pk order disagrees with date order."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
    )
    # Lower pk, *later* dates — entered first.
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan, name="March week", date_from=date(2024, 3, 1), date_to=date(2024, 3, 7)
        ),
        min_party=1,
        max_party=8,
        nightly=Decimal("150.00"),
    )
    # Higher pk, earlier dates; spans Feb 29 so its mapped range collides on 1 Mar.
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan, name="Late Feb", date_from=date(2024, 2, 25), date_to=date(2024, 2, 29)
        ),
        min_party=1,
        max_party=8,
        nightly=Decimal("100.00"),
    )

    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(2025, 2, 1),
        currency=gbp,
        date_map=keep_calendar_date,
    )
    assert ctx is not None

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2025, currency=gbp, date_map=keep_calendar_date
    )
    mat_periods = list(
        RatePeriod.objects.filter(plan=new_plan, is_active=True, date_from__year=2025).order_by(
            "date_from", "pk"
        )
    )
    mat_rules = {p.pk: list(p.bands.all()) for p in mat_periods}

    for night in nights(date(2025, 2, 25), date(2025, 3, 8)):
        projected = pick_band_for_night(ctx.periods, ctx.bands_by_period, night, party=4)
        materialised = pick_band_for_night(mat_periods, mat_rules, night, party=4)
        assert type(projected) is type(materialised), night
        if isinstance(projected, Picked):
            assert isinstance(materialised, Picked)
            assert rule_nightly(projected.rule) == rule_nightly(materialised.rule), night


@pytest.mark.django_db
def test_materialise_carries_anchor_period_min_max_nights(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """The materialised period inherits the anchor period's nullable min/max-nights
    (GAP-056 — parity with projection, which copies them). NULL would silently
    drop a seasonal min-stay when a promoted year is later edited."""
    anchor_period = anchor_rule.period
    assert anchor_period is not None
    anchor_period.min_nights, anchor_period.max_nights = 5, 14
    anchor_period.save(update_fields=["min_nights", "max_nights"])

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2028, currency=gbp, date_map=keep_calendar_date
    )
    carried = RatePeriod.objects.get(plan=new_plan, date_from=date(2028, 6, 1))
    assert carried.min_nights == 5
    assert carried.max_nights == 14


@pytest.mark.django_db
def test_materialise_copies_source_period_names(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """GAP-059: a carried period keeps its curated operator label when every
    band in its segment descends from one source period (the common,
    no-collision carry) — annual carry-forward must not destroy names."""
    new_plan = RateCarryoverService.materialise(
        property_, target_year=2028, currency=gbp, date_map=keep_calendar_date
    )
    carried = RatePeriod.objects.get(plan=new_plan, date_from__year=2028)
    assert carried.name == "Peak"  # the anchor fixture's period label


@pytest.mark.django_db
def test_materialise_derives_name_when_segment_mixes_source_periods(
    property_: Property, gbp: Currency
) -> None:
    """GAP-059: when date-mapping regroups bands from *different* source
    periods into one segment, there is no single name to copy — the segment
    falls back to the date-span placeholder (same derivation as the loader
    and the 0017 backfill).

    Setup mirrors the Feb-29 collision tests: the leap-day span lands one day
    onto its neighbour after mapping, but here the bands are party-disjoint so
    neither is clipped — the shared day becomes a mixed-parentage segment."""
    plan = RatePlan.objects.create(
        property=property_,
        name="2024",
        currency=gbp,
    )
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan,
            name="Late Feb",
            date_from=date(2024, 2, 25),
            date_to=date(2024, 2, 29),  # spans Feb 29
        ),
        min_party=1,
        max_party=4,
        nightly=Decimal("100.00"),
    )
    RateBand.objects.create(
        period=RatePeriod.objects.create(
            plan=plan, name="Early March", date_from=date(2024, 3, 1), date_to=date(2024, 3, 7)
        ),
        min_party=5,
        max_party=8,
        nightly=Decimal("150.00"),
    )

    new_plan = RateCarryoverService.materialise(
        property_, target_year=2025, currency=gbp, date_map=keep_calendar_date
    )

    names = list(
        RatePeriod.objects.filter(plan=new_plan, date_from__year=2025)
        .order_by("date_from")
        .values_list("name", flat=True)
    )
    # 2/25-2/28 is purely "Late Feb"; 3/1 mixes both parents (placeholder);
    # 3/2-3/7 is purely "Early March".
    sliver = derive_period_name(date(2025, 3, 1), date(2025, 3, 1))
    assert names == ["Late Feb", sliver, "Early March"]


# --- Q-018: reductions are a this-year fact ---------------------------------


@pytest.mark.django_db
def test_materialise_drops_reductions_and_carries_base(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """The ticket's acceptance test: discounted 2026 → undiscounted 2027.

    Carry-over copies the *base* prices and never the reduction columns —
    the whole point of Q-018's base-plus-reduction split.
    """
    # Fixed-amount shape here; the uplift test below (and the projection /
    # duplicate pins) cover the percent shape.
    anchor_rule.weekly = Decimal("1300.00")
    anchor_rule.reduced_nightly = Decimal("150.00")
    anchor_rule.reduced_weekly = Decimal("1000.00")
    anchor_rule.reduced_at = date(2026, 5, 1)
    anchor_rule.reduction_reason = "Slow season"
    anchor_rule.save()

    new_plan = RateCarryoverService.materialise(
        property_,
        target_year=2027,
        currency=gbp,
        date_map=keep_calendar_date,
    )

    band = RateBand.objects.get(period__plan=new_plan, period__date_from__year=2027)
    assert band.nightly == Decimal("200.00")
    assert band.weekly == Decimal("1300.00")
    assert band.reduction_percent is None
    assert band.reduced_nightly is None
    assert band.reduced_weekly is None
    assert band.reduced_at is None
    assert band.reduction_reason == ""
    assert band.has_reduction is False


@pytest.mark.django_db
def test_materialise_uplift_applies_to_base_not_effective(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    anchor_rule.reduction_percent = Decimal("50.00")
    anchor_rule.save()

    new_plan = RateCarryoverService.materialise(
        property_,
        target_year=2027,
        currency=gbp,
        date_map=keep_calendar_date,
        uplift=Decimal("0.10"),
    )

    band = RateBand.objects.get(period__plan=new_plan, period__date_from__year=2027)
    # 10% on the base 200.00 — never on the reduced 100.00.
    assert band.nightly == Decimal("220.00")
    assert band.has_reduction is False


# --- GAP-114: carried rows are indicative until the owner confirms them ------


@pytest.mark.django_db
def test_materialise_writes_indicative_bands(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """A carry-forward is a copy nobody has signed off (decision 5): every band
    it writes is `is_indicative=True`, whatever the anchor's own flag."""
    assert anchor_rule.is_indicative is False
    new_plan = RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)

    carried = RateBand.objects.filter(period__plan=new_plan, period__date_from__year=2028)
    assert carried.exists()
    assert all(band.is_indicative for band in carried)
    anchor_rule.refresh_from_db()
    assert anchor_rule.is_indicative is False


@pytest.mark.django_db
def test_materialise_rerun_keeps_confirmed_bands_confirmed(
    property_: Property, gbp: Currency, anchor_rule: RateBand
) -> None:
    """The idempotent early return leaves existing rows alone — a band staff
    have since confirmed is not re-flagged by a repeat carry-forward."""
    RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)
    band = RateBand.objects.get(period__date_from__year=2028)
    band.is_indicative = False
    band.save(update_fields=["is_indicative"])

    RateCarryoverService.materialise(property_, target_year=2028, currency=gbp)

    band.refresh_from_db()
    assert band.is_indicative is False
