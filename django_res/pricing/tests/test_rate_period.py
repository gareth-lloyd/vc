"""Tests for `pricing.models.rate.RatePeriod` invariants (GAP-056).

A `RatePeriod` owns a plan's date window with inclusive dates (single-day
allowed, `date_from <= date_to`). Periods on one plan are date-disjoint
(`rateperiod_no_overlap` EXCLUDE, contract constraint from Unit 9).
"""

from __future__ import annotations

from datetime import date
from typing import cast

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from pricing.factories import RatePlanFactory
from pricing.models import Currency, RatePeriod, RatePlan


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


# --- GAP-110 U1: denormalised regime columns -------------------------------
#
# `RatePeriod.property` / `.currency` mirror the owning plan so the regime-wide
# EXCLUDE (Unit 4) can partition on them — Postgres can't join through `plan`
# inside a constraint. They are derived: `save()` stamps them from the plan and
# ignores whatever the caller supplied.


@pytest.mark.django_db
def test_rateperiod_save_stamps_property_and_currency_from_plan(plan: RatePlan) -> None:
    period = RatePeriod.objects.create(
        plan=plan, name="June", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    period.refresh_from_db()
    assert period.property_id == plan.property_id
    assert period.currency_id == plan.currency_id


@pytest.mark.django_db
def test_rateperiod_save_overrides_supplied_regime_values(plan: RatePlan, usd: Currency) -> None:
    """The stamps are never an input: a caller passing a foreign property or
    currency gets the plan's values, silently."""
    other = cast(RatePlan, RatePlanFactory())
    period = RatePeriod.objects.create(
        plan=plan,
        property=other.property,
        currency=usd,
        name="June",
        date_from=date(2026, 6, 1),
        date_to=date(2026, 6, 30),
    )
    period.refresh_from_db()
    assert period.property_id == plan.property_id
    assert period.currency_id == plan.currency_id


@pytest.mark.django_db
def test_rateperiod_save_restamps_when_plan_changes(plan: RatePlan) -> None:
    """Moving a period to another plan re-derives the stamps, even under
    `update_fields=["plan"]`."""
    period = RatePeriod.objects.create(
        plan=plan, name="June", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    other = cast(RatePlan, RatePlanFactory())
    period.plan = other
    period.save(update_fields=["plan"])
    period.refresh_from_db()
    assert period.property_id == other.property_id
    assert period.currency_id == other.currency_id


@pytest.mark.django_db
def test_rateperiod_partial_save_without_plan_leaves_stamps_alone(plan: RatePlan) -> None:
    """Stamps only ever land together with `plan_id`: a partial save that
    doesn't write `plan` neither re-derives them nor widens `update_fields`."""
    period = RatePeriod.objects.create(
        plan=plan, name="June", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    period.plan = cast(RatePlan, RatePlanFactory())  # in-memory only
    period.name = "Renamed"
    period.save(update_fields=["name"])
    period.refresh_from_db()
    assert period.name == "Renamed"
    assert period.plan_id == plan.pk
    assert period.property_id == plan.property_id
    assert period.currency_id == plan.currency_id


@pytest.mark.django_db
def test_rateplan_currency_locked_once_periods_exist(plan: RatePlan, usd: Currency) -> None:
    """A plan with periods is a regime with stamped children: changing its
    currency would orphan the stamps, so `clean()` (admin/forms) refuses."""
    plan.full_clean()  # periodless: free to change
    RatePeriod.objects.create(
        plan=plan, name="June", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    plan.currency = usd
    with pytest.raises(ValidationError) as excinfo:
        plan.full_clean()
    assert "currency" in excinfo.value.error_dict


@pytest.mark.django_db
def test_rateplan_property_locked_once_periods_exist(plan: RatePlan) -> None:
    """The other half of the regime key: moving a plan with periods to another
    property is refused for the same reason."""
    RatePeriod.objects.create(
        plan=plan, name="June", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    plan.property = cast(RatePlan, RatePlanFactory()).property
    with pytest.raises(ValidationError) as excinfo:
        plan.full_clean()
    assert "property" in excinfo.value.error_dict


@pytest.mark.django_db
def test_rateplan_clean_allows_same_currency_with_periods(plan: RatePlan) -> None:
    RatePeriod.objects.create(
        plan=plan, name="June", date_from=date(2026, 6, 1), date_to=date(2026, 6, 30)
    )
    plan.name = "Renamed"
    plan.full_clean()  # no raise
