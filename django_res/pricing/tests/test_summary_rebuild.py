"""The RateRule/RatePlan → VillaPricingSummary rebuild is async.

Edits enqueue a Celery rebuild on commit instead of recomputing inline in
the request transaction — a bulk rule edit or CSV re-import must not pay
N synchronous rebuilds.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pricing.models import RateCard, RateRule, VillaPricingSummary

pytestmark = pytest.mark.django_db


@pytest.fixture
def rule(card: RateCard) -> RateRule:
    return RateRule.objects.create(
        card=card,
        date_from="2026-07-01",
        date_to="2026-07-31",
        min_party=1,
        max_party=8,
        nightly=Decimal("250.00"),
        weekly=Decimal("1500.00"),
    )


@pytest.mark.usefixtures("run_on_commit_immediately")
def test_raterule_save_rebuilds_summary_after_commit(rule: RateRule) -> None:
    plan = rule.card.plan
    summary = VillaPricingSummary.objects.get(
        property_id=plan.property_id, currency_id=plan.currency_id
    )
    assert summary.min_nightly == Decimal("250.00")
    assert summary.max_party == 8


def test_raterule_save_defers_rebuild_to_commit(rule: RateRule) -> None:
    """Without the commit hooks running, no rebuild may have happened —
    pins that the recompute is on_commit + Celery, not inline."""
    plan = rule.card.plan
    assert not VillaPricingSummary.objects.filter(
        property_id=plan.property_id, currency_id=plan.currency_id
    ).exists()
