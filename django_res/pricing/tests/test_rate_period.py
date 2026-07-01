"""Tests for `pricing.models.rate.RatePeriod` invariants (GAP-056).

A `RatePeriod` owns a plan's date window with inclusive dates (single-day
allowed, `date_from <= date_to`). The periods-disjoint-per-plan EXCLUDE is a
*contract* constraint added in Unit 9 (once the card-precedence engine and the
loader stop producing transitionally-overlapping periods) — its tests live
there, not here.
"""

from __future__ import annotations

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from pricing.models import RatePeriod, RatePlan


@pytest.mark.django_db
def test_rateperiod_allows_single_day(plan: RatePlan) -> None:
    """Inclusive dates: `date_from == date_to` is a legitimate one-day period."""
    period = RatePeriod.objects.create(
        plan=plan,
        date_from=date(2026, 6, 10),
        date_to=date(2026, 6, 10),
    )
    assert period.pk is not None


@pytest.mark.django_db
def test_rateperiod_rejects_inverted_range(plan: RatePlan) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        RatePeriod.objects.create(
            plan=plan,
            date_from=date(2026, 7, 1),
            date_to=date(2026, 6, 1),
        )
