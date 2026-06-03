"""Tests for lazy rate projection (date-map functions + RateProjectionService)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pricing.models import Currency, RateCard, RatePlan, RateRule
from pricing.services.projection import (
    RateProjectionService,
    keep_calendar_date,
    shift_to_changeover_weekday,
)
from properties.models import Property

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
def anchor_plan(property_: Property, gbp: Currency) -> RateRule:
    """A 2026 plan/card/rule to act as the projection anchor."""
    plan = RatePlan.objects.create(
        property=property_,
        name="Summer 2026",
        currency=gbp,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
    )
    card = RateCard.objects.create(plan=plan, name="Default", sort_order=0)
    return RateRule.objects.create(
        card=card,
        date_from=date(2026, 6, 1),
        date_to=date(2026, 8, 31),
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )


@pytest.mark.django_db
def test_find_anchor_returns_most_recent_prior_plan(
    property_: Property, gbp: Currency, anchor_plan: RateRule
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
    property_: Property, gbp: Currency, usd: Currency, anchor_plan: RateRule
) -> None:
    found = RateProjectionService.find_anchor_plan(property_, usd, date(2028, 7, 4))
    assert found is None


@pytest.mark.django_db
def test_find_anchor_none_for_brand_new_villa(property_: Property, gbp: Currency) -> None:
    found = RateProjectionService.find_anchor_plan(property_, gbp, date(2028, 7, 4))
    assert found is None


@pytest.mark.django_db
def test_find_anchor_excludes_same_year_plan(
    property_: Property, gbp: Currency, anchor_plan: RateRule
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
    property_: Property, gbp: Currency, anchor_plan: RateRule
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
    assert ctx.plan.pk == anchor_plan.card.plan.pk
    assert RatePlan.objects.count() == 1
    [rule] = ctx.rules_by_card[anchor_plan.card.pk]
    assert rule.pk == anchor_plan.pk
    assert rule.date_from == date(2028, 6, 1)
    assert rule.date_to == date(2028, 8, 31)
    assert rule.nightly == Decimal("200.00")
    assert ctx.projection == {
        "source_plan_id": anchor_plan.card.plan.pk,
        "source_year": 2026,
        "target_year": 2028,
        "uplift_pct": "0.00",
        "date_map": "keep_calendar_date",
    }


@pytest.mark.django_db
def test_project_applies_uplift(property_: Property, gbp: Currency, anchor_plan: RateRule) -> None:
    ctx = RateProjectionService.project(
        property=property_,
        date_from=date(2028, 7, 4),
        currency=gbp,
        date_map=keep_calendar_date,
        uplift=Decimal("0.05"),
    )
    assert ctx is not None
    assert ctx.projection is not None
    [rule] = ctx.rules_by_card[anchor_plan.card.pk]
    assert rule.nightly == Decimal("210.00")
    assert ctx.projection["uplift_pct"] == "5.00"


@pytest.mark.django_db
def test_project_preserves_poa(property_: Property, gbp: Currency, anchor_plan: RateRule) -> None:
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
    [rule] = ctx.rules_by_card[poa.card.pk]
    assert rule.is_poa is True
    assert rule.nightly is None


@pytest.mark.django_db
def test_project_skips_unapproved_rules(
    property_: Property, gbp: Currency, anchor_plan: RateRule
) -> None:
    RateRule.objects.create(
        card=anchor_plan.card,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 9, 30),
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
    assert len(ctx.rules_by_card[anchor_plan.card.pk]) == 1


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
