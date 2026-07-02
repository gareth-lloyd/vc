"""Tests for `pricing.models.rate.RatePeriod` invariants (GAP-056).

A `RatePeriod` owns a plan's date window with inclusive dates (single-day
allowed, `date_from <= date_to`). Periods on one plan are date-disjoint
(`rateperiod_no_overlap` EXCLUDE, contract constraint from Unit 9).
"""

from __future__ import annotations

from datetime import date
from typing import cast

import pytest
from django.db import IntegrityError, transaction

from pricing.factories import RatePlanFactory
from pricing.models import RatePeriod, RatePlan


@pytest.mark.django_db
def test_rateperiod_allows_single_day(plan: RatePlan) -> None:
    """Inclusive dates: `date_from == date_to` is a legitimate one-day period."""
    period = RatePeriod.objects.create(
        plan=plan,
        name="Single day",
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 10),
    )
    assert period.pk is not None


@pytest.mark.django_db
def test_rateperiod_rejects_inverted_range(plan: RatePlan) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RatePeriod.objects.create(
            plan=plan,
            name="Inverted",
            date_from=date(2026, 7, 1),
            date_to=date(2026, 6, 1),
        )


@pytest.mark.django_db
def test_rateperiod_no_overlap_same_plan(plan: RatePlan) -> None:
    """Two periods on one plan with overlapping dates are forbidden."""
    RatePeriod.objects.create(
        plan=plan, name="June", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RatePeriod.objects.create(
            plan=plan, name="Overlap", date_from=date(2026, 6, 15), date_to=date(2026, 7, 15)
        )


@pytest.mark.django_db
def test_rateperiod_no_overlap_is_inclusive_on_boundaries(plan: RatePlan) -> None:
    """Dates are inclusive: a period starting on another's end date overlaps."""
    RatePeriod.objects.create(
        plan=plan, name="June", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RatePeriod.objects.create(
            plan=plan, name="Boundary", date_from=date(2026, 6, 30), date_to=date(2026, 7, 31)
        )


@pytest.mark.django_db
def test_rateperiod_overlap_allowed_across_plans() -> None:
    """The EXCLUDE is per-plan: two plans may share a date window."""
    plan_a = cast(RatePlan, RatePlanFactory())
    plan_b = cast(RatePlan, RatePlanFactory())
    RatePeriod.objects.create(
        plan=plan_a, name="June A", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    other = RatePeriod.objects.create(
        plan=plan_b, name="June B", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    assert other.pk is not None


@pytest.mark.django_db
def test_rateperiod_rejects_blank_name(plan: RatePlan) -> None:
    """GAP-059: the operator label is structurally compulsory — a bare
    `objects.create()` without a name trips the CHECK, not just the API."""
    with pytest.raises(IntegrityError), transaction.atomic():
        RatePeriod.objects.create(
            plan=plan,
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 31),
        )
