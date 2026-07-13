"""Clone services for pricing rows (SMELL-009).

The `:duplicate` endpoints' clone walks, extracted from the views, plus
FG-010 idempotency: an optional `idempotency_key` dedupes retries via a
parent-scoped pre-check (`core.idempotency.find_by_key`) backed by a
partial-unique constraint on the model. `rates.py` / `extras.py` stay
pure-math; state-mutating clone logic lives here (mirroring `carryover.py`).

Like `PropertyLifecycleService.duplicate` (the exemplar), these take no
`actor` and do no permission checks — authorization is the view permission
class's job for now (deliberate SMELL-008 leftover).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from core.idempotency import find_by_key
from pricing.models import Extra, RateBand, RatePeriod, RatePlan

if TYPE_CHECKING:
    from properties.models import Property

__all__ = ["duplicate_extra", "duplicate_rate_plan"]


def duplicate_extra(
    extra: Extra,
    *,
    target_property: Property | None = None,
    idempotency_key: str | None = None,
) -> Extra:
    """Clone an extra, optionally onto another property.

    The idempotency pre-check scopes to the DESTINATION property — the same
    key aimed at a different `target_property` is a different logical
    operation and clones again (pinned by test). A retry with the same key
    and target returns the original clone; a racing loser past the pre-check
    trips `extra_idempotency_key_unique_per_property` with `IntegrityError`
    for the view to map to 409. (Extra has no `legacy_id`, so there is
    nothing to null here.)
    """
    destination = target_property or extra.property
    existing = find_by_key(Extra.objects.filter(property=destination), idempotency_key)
    if existing is not None:
        return existing

    with transaction.atomic():
        clone = Extra.objects.get(pk=extra.pk)
        clone.pk = None
        clone.property = destination
        clone.name = f"{extra.name} (copy)"
        clone.idempotency_key = idempotency_key or ""
        clone.save()
    return clone


def duplicate_rate_plan(plan: RatePlan, *, idempotency_key: str | None = None) -> RatePlan:
    """Clone a plan and its whole period/band grid onto a new plan.

    A retry carrying the same `idempotency_key` returns the original clone
    untouched (pre-check outside the atomic block, so a retry never re-runs
    the child walk); a racing loser past the pre-check trips
    `rateplan_idempotency_key_unique_per_property` with `IntegrityError`
    for the view to map to 409.

    `legacy_id` is deliberately NOT copied on any level: active loaders
    upsert on it, so a copied one would make the next delta load rewrite
    the clone instead of the imported original.
    """
    existing = find_by_key(RatePlan.objects.filter(property=plan.property), idempotency_key)
    if existing is not None:
        return existing

    with transaction.atomic():
        source_pk = plan.pk
        clone = RatePlan.objects.get(pk=source_pk)
        clone.pk = None
        clone.name = f"{plan.name} (copy)"
        clone.legacy_id = None
        clone.idempotency_key = idempotency_key or ""
        clone.save()
        # GAP-056: each cloned band re-parents to the cloned period (which
        # owns the dates) — never the source plan's period. The loop rows are
        # service-owned queryset instances, so they're mutated in place.
        for period in RatePeriod.objects.filter(plan_id=source_pk):
            source_period_pk = period.pk
            period.pk = None
            period.plan = clone
            period.legacy_id = None
            period.save()
            for band in RateBand.objects.filter(period_id=source_period_pk):
                band.pk = None
                band.period = period
                band.legacy_id = None
                band.save()
    return clone
