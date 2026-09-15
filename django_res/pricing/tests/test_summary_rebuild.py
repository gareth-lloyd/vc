"""The RateBand/RatePlan → VillaPricingSummary rebuild is async.

Edits enqueue a Celery rebuild on commit instead of recomputing inline in
the request transaction — a bulk rule edit or CSV re-import must not pay
N synchronous rebuilds.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command

from pricing.models import Currency, RateBand, RatePeriod, RatePlan, VillaPricingSummary
from pricing.signals import summary_rebuild_suppressed, suppress_summary_rebuild
from pricing.tasks import rebuild_summary
from properties.enums import PriceBasis
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


# ---------------------------------------------------------------------------
# GAP-108: `suppress_summary_rebuild` + the `rebuild_summaries` command
# ---------------------------------------------------------------------------


def _band_for(plan: RatePlan) -> RateBand:
    period = RatePeriod.objects.create(
        plan=plan, name="August", date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)
    )
    return RateBand.objects.create(
        period=period, min_party=1, max_party=6, nightly=Decimal("300.00")
    )


def test_rateplan_and_band_edits_enqueue_a_rebuild_without_suppression(
    plan: RatePlan, django_capture_on_commit_callbacks: Any
) -> None:
    """Positive control for the suppression tests below."""
    with (
        patch("pricing.signals.rebuild_summary_task.delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        plan.save()
        _band_for(plan)
    assert delay.call_count == 2


def test_suppressed_rateplan_and_band_saves_and_deletes_enqueue_nothing(
    plan: RatePlan, django_capture_on_commit_callbacks: Any
) -> None:
    with (
        patch("pricing.signals.rebuild_summary_task.delay") as delay,
        django_capture_on_commit_callbacks(execute=True) as callbacks,
        suppress_summary_rebuild(),
    ):
        plan.save()
        band = _band_for(plan)
        band.save()
        band.delete()
        plan.delete()
    assert callbacks == []
    delay.assert_not_called()


def test_suppression_flag_is_restored_on_exit_including_nested() -> None:
    assert summary_rebuild_suppressed() is False
    with suppress_summary_rebuild():
        assert summary_rebuild_suppressed() is True
        with suppress_summary_rebuild():
            assert summary_rebuild_suppressed() is True
        assert summary_rebuild_suppressed() is True  # inner exit keeps the outer flag
    assert summary_rebuild_suppressed() is False


def test_suppression_flag_is_restored_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError), suppress_summary_rebuild():
        raise RuntimeError("boom")
    assert summary_rebuild_suppressed() is False


def test_rebuild_summaries_command_builds_one_row_per_property_currency(
    plan: RatePlan, usd: Currency, capsys: pytest.CaptureFixture[str]
) -> None:
    """Loads run with the rebuild suppressed, so the cutover backfills the
    display cache with one synchronous pass over every (property, currency)."""
    with suppress_summary_rebuild():
        _band_for(plan)  # GBP: one band, 300 nightly, party 1-6
        usd_plan = RatePlan.objects.create(
            property=plan.property, name="Summer USD", currency=usd, prices_by_occupancy=True
        )
        usd_period = RatePeriod.objects.create(
            plan=usd_plan, name="July", date_from=date(2026, 7, 1), date_to=date(2026, 7, 31)
        )
        for lo, hi, nightly in ((1, 4, "400.00"), (5, 10, "550.00")):
            RateBand.objects.create(
                period=usd_period, min_party=lo, max_party=hi, nightly=Decimal(nightly)
            )
        # A second GBP plan on the same villa must not produce a duplicate row.
        RatePlan.objects.create(
            property=plan.property,
            name="Winter GBP",
            currency=plan.currency,
            price_basis=PriceBasis.NET,
            prices_by_occupancy=True,
        )
    assert not VillaPricingSummary.objects.exists()

    call_command("rebuild_summaries")

    rows = {s.currency_id: s for s in VillaPricingSummary.objects.all()}
    assert set(rows) == {plan.currency_id, usd.id}
    gbp_row, usd_row = rows[plan.currency_id], rows[usd.id]
    assert (gbp_row.min_nightly, gbp_row.max_nightly) == (Decimal("300.00"), Decimal("300.00"))
    assert (gbp_row.min_party, gbp_row.max_party) == (1, 6)
    assert (usd_row.min_nightly, usd_row.max_nightly) == (Decimal("400.00"), Decimal("550.00"))
    assert (usd_row.min_party, usd_row.max_party) == (1, 10)
    assert "Rebuilt 2 pricing summaries" in capsys.readouterr().out
