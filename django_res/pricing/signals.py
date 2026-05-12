"""Pricing signal handlers.

Rebuild the `VillaPricingSummary` cache on every RateRule / RatePlan edit.

TODO: replace the synchronous `rebuild_summary` call with a debounced
Celery task once Celery is wired. The debounce window collapses bursts of
edits (e.g. a CSV re-import) into one rebuild per (property, currency).
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from pricing.models import RatePlan, RateRule
from pricing.tasks import rebuild_summary


@receiver(post_save, sender=RateRule)
@receiver(post_delete, sender=RateRule)
def _on_raterule_change(sender: type, instance: RateRule, **_: Any) -> None:
    plan = instance.card.plan if instance.card_id else None
    if plan is None:
        return
    rebuild_summary(property_id=plan.property_id, currency_id=plan.currency_id)


@receiver(post_save, sender=RatePlan)
@receiver(post_delete, sender=RatePlan)
def _on_rateplan_change(sender: type, instance: RatePlan, **_: Any) -> None:
    rebuild_summary(property_id=instance.property_id, currency_id=instance.currency_id)
