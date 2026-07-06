"""Backfill guard for pricing migration 0013 (BUG-016 Unit 6).

`backfill_plan_periods` is callable only with 0013's historical models (HEAD
RateBand lost `card`/own dates in GAP-056), so it is driven through
`MigrationExecutor` like the 0011 guard: seed RateCard/RateRule rows at the
pre-0013 state, migrate forward across 0013, assert the periods appear and the
rules point at them.

Seeding constraints at the BEFORE state: the strict `raterule_date_from_lt_date_to`
CHECK makes inverted spans unseedable (the invalid-span orphan path is
untestable through the migration), and the per-card `raterule_no_overlap`
EXCLUDE forces colliding rules onto different cards of the same plan — which is
the real pre-0013 collision scenario (card precedence).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.state import ProjectState

from pricing.services.period_backfill import BackfillResult, backfill_plan_periods

_BEFORE = [
    ("pricing", "0012_drop_rateplan_inclusion"),
    ("properties", "0024_propertyservice"),
]
_AFTER = [("pricing", "0013_rateperiod_hierarchy")]


def _migrate(targets: list[tuple[str, str]]) -> ProjectState:
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    executor.loader.build_graph()
    return executor.loader.project_state(targets)


def _seed_plan(apps_state: ProjectState, slug: str) -> Any:
    Country = apps_state.apps.get_model("properties", "Country")
    Region = apps_state.apps.get_model("properties", "Region")
    PropertyCategory = apps_state.apps.get_model("properties", "PropertyCategory")
    PropertyGroup = apps_state.apps.get_model("properties", "PropertyGroup")
    Property = apps_state.apps.get_model("properties", "Property")
    Currency = apps_state.apps.get_model("pricing", "Currency")
    RatePlan = apps_state.apps.get_model("pricing", "RatePlan")

    country = Country.objects.get(iso2="GB")  # seeded by properties/0009
    region, _ = Region.objects.get_or_create(country=country, name="Cornwall", slug="cornwall")
    cat, _ = PropertyCategory.objects.get_or_create(name="Villa", slug="villa")
    group, _ = PropertyGroup.objects.get_or_create(name="G")
    prop = Property.objects.create(
        name="P", display_name="P", slug=slug, category=cat, group=group, region=region
    )
    cur, _ = Currency.objects.get_or_create(code="EUR", defaults={"name": "Euro", "symbol": "€"})
    return RatePlan.objects.create(
        property=prop, currency=cur, name="Std", effective_from=date(2027, 1, 1)
    )


def _seed_rule(apps_state: ProjectState, plan: Any, card_name: str, **rule_kwargs: object) -> Any:
    RateCard = apps_state.apps.get_model("pricing", "RateCard")
    RateRule = apps_state.apps.get_model("pricing", "RateRule")
    card, _ = RateCard.objects.get_or_create(plan=plan, name=card_name)
    rule_kwargs.setdefault("nightly", Decimal("100.00"))
    return RateRule.objects.create(card=card, **rule_kwargs)


@pytest.mark.django_db(transaction=True)
def test_non_ragged_rules_share_one_period() -> None:
    before = _migrate(_BEFORE)
    try:
        plan = _seed_plan(before, slug="p-nonragged")
        _seed_rule(
            before,
            plan,
            "C1",
            date_from=date(2027, 1, 1),
            date_to=date(2027, 1, 31),
            min_party=1,
            max_party=4,
            legacy_id="r1",
        )
        _seed_rule(
            before,
            plan,
            "C1",  # party-disjoint, so the per-card EXCLUDE allows one card
            date_from=date(2027, 1, 1),
            date_to=date(2027, 1, 31),
            min_party=5,
            max_party=8,
            nightly=Decimal("200.00"),
            legacy_id="r2",
        )

        after = _migrate(_AFTER)
        RatePeriod = after.apps.get_model("pricing", "RatePeriod")
        RateRule = after.apps.get_model("pricing", "RateRule")

        period = RatePeriod.objects.get(plan_id=plan.pk)
        assert (period.date_from, period.date_to) == (date(2027, 1, 1), date(2027, 1, 31))
        rules = list(RateRule.objects.filter(card__plan_id=plan.pk))
        assert len(rules) == 2  # no fragments
        assert all(rule.period_id == period.pk for rule in rules)
        assert not any("#seg" in (rule.legacy_id or "") for rule in rules)
    finally:
        call_command("migrate", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_ragged_rule_fragments_with_seg_namespacing() -> None:
    before = _migrate(_BEFORE)
    try:
        plan = _seed_plan(before, slug="p-ragged")
        rule_b = _seed_rule(
            before,
            plan,
            "C1",
            date_from=date(2027, 1, 1),
            date_to=date(2027, 1, 31),
            min_party=1,
            max_party=4,
            legacy_id="B",
        )
        rule_a = _seed_rule(
            before,
            plan,
            "C2",
            date_from=date(2027, 1, 10),
            date_to=date(2027, 1, 20),
            min_party=5,
            max_party=8,
            nightly=Decimal("200.00"),
            legacy_id="A",
        )

        after = _migrate(_AFTER)
        RatePeriod = after.apps.get_model("pricing", "RatePeriod")
        RateRule = after.apps.get_model("pricing", "RateRule")

        spans = list(
            RatePeriod.objects.filter(plan_id=plan.pk)
            .order_by("date_from")
            .values_list("date_from", "date_to")
        )
        assert spans == [
            (date(2027, 1, 1), date(2027, 1, 9)),
            (date(2027, 1, 10), date(2027, 1, 20)),
            (date(2027, 1, 21), date(2027, 1, 31)),
        ]

        # Original B keeps its pk on the first segment, dates rewritten.
        first_b = RateRule.objects.get(pk=rule_b.pk)
        assert first_b.legacy_id == "B"
        assert (first_b.date_from, first_b.date_to) == (date(2027, 1, 1), date(2027, 1, 9))
        assert (first_b.min_party, first_b.max_party) == (1, 4)

        seg1 = RateRule.objects.get(legacy_id="B#seg1")
        assert (seg1.date_from, seg1.date_to) == (date(2027, 1, 10), date(2027, 1, 20))
        seg2 = RateRule.objects.get(legacy_id="B#seg2")
        assert (seg2.date_from, seg2.date_to) == (date(2027, 1, 21), date(2027, 1, 31))
        for clone in (seg1, seg2):
            assert (clone.min_party, clone.max_party) == (1, 4)
            assert clone.nightly == Decimal("100.00")

        pointed_a = RateRule.objects.get(pk=rule_a.pk)
        assert (pointed_a.date_from, pointed_a.date_to) == (date(2027, 1, 10), date(2027, 1, 20))
        assert RateRule.objects.filter(legacy_id__startswith="A#").count() == 0
        assert RateRule.objects.filter(card__plan_id=plan.pk).count() == 4
        assert RateRule.objects.filter(card__plan_id=plan.pk, period__isnull=True).count() == 0
    finally:
        call_command("migrate", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_fully_shadowed_rule_stays_orphaned() -> None:
    before = _migrate(_BEFORE)
    try:
        plan = _seed_plan(before, slug="p-shadowed")
        winner = _seed_rule(
            before,
            plan,
            "C1",  # lower pk: created first, wins the whole grid
            date_from=date(2027, 2, 1),
            date_to=date(2027, 2, 28),
            min_party=1,
            max_party=6,
            legacy_id="W",
        )
        loser = _seed_rule(
            before,
            plan,
            "C2",
            date_from=date(2027, 2, 1),
            date_to=date(2027, 2, 28),
            min_party=1,
            max_party=6,
            nightly=Decimal("999.00"),
            legacy_id="L",
        )

        after = _migrate(_AFTER)
        RatePeriod = after.apps.get_model("pricing", "RatePeriod")
        RateRule = after.apps.get_model("pricing", "RateRule")

        period = RatePeriod.objects.get(plan_id=plan.pk)
        assert RateRule.objects.get(pk=winner.pk).period_id == period.pk
        assert RateRule.objects.get(pk=loser.pk).period_id is None
        assert RateRule.objects.filter(card__plan_id=plan.pk).count() == 2  # no clone

        # 0015 (applied on the way back to head) makes `period` non-null, so the
        # deliberately-orphaned loser must be removed before the restore.
        RateRule.objects.filter(pk=loser.pk).delete()
    finally:
        call_command("migrate", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_backfill_rerun_is_idempotent() -> None:
    before = _migrate(_BEFORE)
    try:
        plan = _seed_plan(before, slug="p-idempotent")
        _seed_rule(
            before,
            plan,
            "C1",
            date_from=date(2027, 1, 1),
            date_to=date(2027, 1, 31),
            min_party=1,
            max_party=4,
            legacy_id="B",
        )
        _seed_rule(
            before,
            plan,
            "C2",
            date_from=date(2027, 1, 10),
            date_to=date(2027, 1, 20),
            min_party=5,
            max_party=8,
            legacy_id="A",
        )

        after = _migrate(_AFTER)
        RatePeriod = after.apps.get_model("pricing", "RatePeriod")
        RateRule = after.apps.get_model("pricing", "RateRule")
        periods_before = RatePeriod.objects.count()
        rules_before = RateRule.objects.count()

        result = backfill_plan_periods(RatePeriod, RateRule)

        assert result == BackfillResult()  # every rule already pointed: all counters zero
        assert RatePeriod.objects.count() == periods_before
        assert RateRule.objects.count() == rules_before
    finally:
        call_command("migrate", verbosity=0)
