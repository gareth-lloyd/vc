"""Pricing signal handlers.

1. Rebuild the `VillaPricingSummary` cache on RateBand / RatePlan edits.
2. Re-push the villa to Zoho when its extras catalogue changes (GAP-102) —
   see the section at the bottom; it rides `enqueue_zoho_push`, not this.

For (1): the rebuild is enqueued on Celery via `transaction.on_commit`, not run
inline: a bulk rule edit or CSV re-import would otherwise pay one full
synchronous rebuild per row inside the request transaction. on_commit
also means a rolled-back edit never triggers a rebuild. Duplicate
enqueues from a burst of edits are harmless — the rebuild is idempotent.
"""

from __future__ import annotations

from operator import attrgetter
from typing import Any

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from pricing.models import Extra, RateBand, RatePlan
from pricing.tasks import rebuild_summary_task
from properties.signals import connect_villa_child


def _enqueue_rebuild(property_id: int, currency_id: int) -> None:
    transaction.on_commit(
        lambda: rebuild_summary_task.delay(property_id, currency_id),
    )


@receiver(post_save, sender=RateBand)
@receiver(post_delete, sender=RateBand)
def _on_raterule_change(sender: type, instance: RateBand, **_: Any) -> None:
    # GAP-056: the band's plan hangs off its RatePeriod. CASCADE delete fires
    # children-first, so the parent period is still present when this runs.
    if instance.period_id is None:
        return
    plan = instance.period.plan
    _enqueue_rebuild(plan.property_id, plan.currency_id)


@receiver(post_save, sender=RatePlan)
@receiver(post_delete, sender=RatePlan)
def _on_rateplan_change(sender: type, instance: RatePlan, **_: Any) -> None:
    _enqueue_rebuild(instance.property_id, instance.currency_id)


# ---------------------------------------------------------------------------
# Extra → Zoho villa re-push (GAP-102)
# ---------------------------------------------------------------------------
# The extras catalogue rides the villa payload (option (a)), so a catalogue
# edit that never touches the Property row must bump the villa's push itself.
# Wired here rather than in `properties.signals._VILLA_CHILDREN` because
# `pricing` sits ABOVE `properties` on the import spine. One villa per extra
# and the PENDING dedupe in `enqueue_zoho_push` collapse a burst of catalogue
# edits into one villa push (never one per booking that used the extra).
connect_villa_child(Extra, attrgetter("property"), uid_prefix="pricing.zoho_flow")
