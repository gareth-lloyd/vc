"""The RateRule/RatePlan → VillaPricingSummary rebuild is async.

Edits enqueue a Celery rebuild on commit instead of recomputing inline in
the request transaction — a bulk rule edit or CSV re-import must not pay
N synchronous rebuilds.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pricing.models import Currency, RateCard, RatePlan, RateRule, VillaPricingSummary
from pricing.tasks import rebuild_summary
from properties.models import Property

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


def test_rebuild_summary_excludes_deactivated_cards_rules(
    property_: Property, gbp: Currency, plan: RatePlan
) -> None:
    """A band under a deactivated RateCard must not seed the display summary —
    the engine excludes it from pricing (transitional card gate), so the summary
    would otherwise advertise a rate no quote will use (GAP-056 U6 review)."""
    withdrawn = RateCard.objects.create(plan=plan, name="Withdrawn", is_active=False)
    RateRule.objects.create(
        card=withdrawn,
        date_from="2026-07-01",
        date_to="2026-07-31",
        min_party=1,
        max_party=8,
        nightly=Decimal("50.00"),
    )
    live = RateCard.objects.create(plan=plan, name="Live")
    RateRule.objects.create(
        card=live,
        date_from="2026-07-01",
        date_to="2026-07-31",
        min_party=1,
        max_party=8,
        nightly=Decimal("200.00"),
    )

    summary = rebuild_summary(property_id=plan.property_id, currency_id=plan.currency_id)
    # Only the live card's 200.00 prices — the withdrawn 50.00 is excluded.
    assert summary.min_nightly == Decimal("200.00")
    assert summary.max_nightly == Decimal("200.00")
