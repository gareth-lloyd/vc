"""The RateBand/RatePlan → VillaPricingSummary rebuild is async.

Edits enqueue a Celery rebuild on commit instead of recomputing inline in
the request transaction — a bulk rule edit or CSV re-import must not pay
N synchronous rebuilds.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from pricing.models import Currency, RateBand, RatePeriod, RatePlan, VillaPricingSummary
from pricing.tasks import rebuild_summary
from properties.models import Property

pytestmark = pytest.mark.django_db


@pytest.fixture
def rule(plan: RatePlan) -> RateBand:
    period = RatePeriod.objects.create(
        plan=plan, name="July", date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
    )
    return RateBand.objects.create(
        period=period,
        min_party=1,
        max_party=8,
        nightly=Decimal("250.00"),
        weekly=Decimal("1500.00"),
    )


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_raterule_save_rebuilds_summary_after_commit(rule: RateBand) -> None:
    plan = rule.period.plan
    summary = VillaPricingSummary.objects.get(
        property_id=plan.property_id, currency_id=plan.currency_id
    )
    assert summary.min_nightly == Decimal("250.00")
    assert summary.max_party == 8


def test_raterule_save_defers_rebuild_to_commit(rule: RateBand) -> None:
    """Without the commit hooks running, no rebuild may have happened —
    pins that the recompute is on_commit + Celery, not inline."""
    plan = rule.period.plan
    assert not VillaPricingSummary.objects.filter(
        property_id=plan.property_id, currency_id=plan.currency_id
    ).exists()


def test_rebuild_summary_excludes_deactivated_period_rules(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    """A band under a deactivated RatePeriod must not seed the display summary —
    the engine excludes it from pricing (period activeness is the sole gate now,
    GAP-056 Unit 9), so the summary would otherwise advertise a rate no quote
    will use."""
    withdrawn = RatePeriod.objects.create(
        plan=plan,
        name="Withdrawn July",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 31),
        is_active=False,
    )
    RateBand.objects.create(
        period=withdrawn,
        min_party=1,
        max_party=8,
        nightly=Decimal("50.00"),
    )
    # A disjoint active period (the periods-disjoint EXCLUDE forbids sharing dates).
    live = RatePeriod.objects.create(
        plan=plan, name="Live August", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)
    )
    RateBand.objects.create(
        period=live,
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )

    summary = rebuild_summary(property_id=plan.property_id, currency_id=plan.currency_id)
    # Only the live period's 200.00 prices — the withdrawn 50.00 is excluded.
    assert summary.min_nightly == Decimal("200.00")
    assert summary.max_nightly == Decimal("200.00")


def test_rebuild_summary_uses_effective_prices(rule: RateBand) -> None:
    """Q-018: the display min/max mirrors what the engine quotes — the
    effective (reduced) prices, not the stored base."""
    plan = rule.period.plan
    rule.reduction_percent = Decimal("20.00")
    rule.save()

    summary = rebuild_summary(property_id=plan.property_id, currency_id=plan.currency_id)

    assert summary.min_nightly == Decimal("200.00")  # 250 - 20%
    assert summary.max_nightly == Decimal("200.00")
    assert summary.min_weekly == Decimal("1200.00")  # 1500 - 20%
    assert summary.max_weekly == Decimal("1200.00")
