"""Pricing signal handlers.

Rebuild the `VillaPricingSummary` cache on RateRule / RatePlan edits.

The rebuild is enqueued on Celery via `transaction.on_commit`, not run
inline: a bulk rule edit or CSV re-import would otherwise pay one full
synchronous rebuild per row inside the request transaction. on_commit
also means a rolled-back edit never triggers a rebuild. Duplicate
enqueues from a burst of edits are harmless — the rebuild is idempotent.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from pricing.models import RatePlan, RateRule
from pricing.tasks import rebuild_summary_task


def _enqueue_rebuild(property_id: int, currency_id: int) -> None:
    transaction.on_commit(
        lambda: rebuild_summary_task.delay(property_id, currency_id),
    )


@receiver(post_save, sender=RateRule)
@receiver(post_delete, sender=RateRule)
def _on_raterule_change(sender: type, instance: RateRule, **_: Any) -> None:
    # GAP-056: the band's plan hangs off its RatePeriod now. The `card` fallback
    # covers the transitional window where a legacy row hasn't been repointed yet
    # (dropped in Unit 9 with the card). CASCADE delete fires children-first, so
    # the parent period/card is still present when this runs.
    period = instance.period if instance.period_id else None
    if period is not None:
        plan = period.plan
    elif instance.card_id:
        plan = instance.card.plan
    else:
        return
    _enqueue_rebuild(plan.property_id, plan.currency_id)


@receiver(post_save, sender=RatePlan)
@receiver(post_delete, sender=RatePlan)
def _on_rateplan_change(sender: type, instance: RatePlan, **_: Any) -> None:
    _enqueue_rebuild(instance.property_id, instance.currency_id)
