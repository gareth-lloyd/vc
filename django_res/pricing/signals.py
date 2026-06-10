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
    plan = instance.card.plan if instance.card_id else None
    if plan is None:
        return
    _enqueue_rebuild(plan.property_id, plan.currency_id)


@receiver(post_save, sender=RatePlan)
@receiver(post_delete, sender=RatePlan)
def _on_rateplan_change(sender: type, instance: RatePlan, **_: Any) -> None:
    _enqueue_rebuild(instance.property_id, instance.currency_id)
