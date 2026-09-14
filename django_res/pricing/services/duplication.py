"""Clone services for pricing rows (SMELL-009).

The `:duplicate` endpoint's clone walk, extracted from the view, plus FG-010
idempotency: an optional `idempotency_key` dedupes retries via a
parent-scoped pre-check (`core.idempotency.find_by_key`) backed by a
partial-unique constraint on the model. `rates.py` / `extras.py` stay
pure-math; state-mutating clone logic lives here (mirroring `carryover.py`).

`RatePlan:duplicate` was removed by GAP-110: a plan is a (property, currency)
regime bucket and at most one prices a night, so a same-context literal copy
has nowhere to live; carry-forward (`carryover.py`) is the year-copy tool.

Like `PropertyLifecycleService.duplicate` (the exemplar), these take no
`actor` and do no permission checks — authorization is the view permission
class's job for now (deliberate SMELL-008 leftover).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from core.idempotency import find_by_key
from pricing.models import Extra

if TYPE_CHECKING:
    from properties.models import Property

__all__ = ["duplicate_extra"]


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
    for the view to map to 409. `legacy_id` is nulled on the clone: the
    active `ExtraLoader` upserts on it (GAP-107), and a copied one would
    make the next legacy load hit two rows.
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
        clone.legacy_id = None
        clone.save()
    return clone
