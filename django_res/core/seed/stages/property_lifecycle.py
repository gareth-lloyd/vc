"""Move a slice of properties into DRAFT / ARCHIVED.

Picks from properties without live bookings so active-overlap invariants
hold. Knob: `pct_property_draft` + `pct_property_archived`. +1 floor when
either is non-zero so small runs always exercise both states.
"""

from __future__ import annotations

from core.seed.context import SeedContext
from core.seed.registry import Stage, register
from properties.services.lifecycle import PropertyLifecycleService


def _run(ctx: SeedContext) -> int:
    if not ctx.properties:
        return 0
    if not (ctx.knobs.pct_property_draft or ctx.knobs.pct_property_archived):
        return 0
    from reservations.enums import OVERLAP_BLOCKING_BOOKING_STATUSES
    from reservations.models.booking import Booking

    # Use the same status set as the `booking_no_overlap_blocking` constraint
    # — PENDING_OWNER_APPROVAL counts here too, otherwise a property mid
    # owner-approval can be archived out from under its booking.
    booking_props = set(
        Booking.objects.filter(status__in=OVERLAP_BLOCKING_BOOKING_STATUSES).values_list(
            "property_id", flat=True
        )
    )
    candidates = [p for p in ctx.properties if p.pk not in booking_props]
    ctx.rng.shuffle(candidates)
    n_draft = (
        max(1, int(len(ctx.properties) * ctx.knobs.pct_property_draft))
        if ctx.knobs.pct_property_draft
        else 0
    )
    n_archived = (
        max(1, int(len(ctx.properties) * ctx.knobs.pct_property_archived))
        if ctx.knobs.pct_property_archived
        else 0
    )
    made = 0
    for prop in candidates[:n_archived]:
        PropertyLifecycleService.archive(prop)
        made += 1
    for prop in candidates[n_archived : n_archived + n_draft]:
        PropertyLifecycleService.archive(prop)
        PropertyLifecycleService.restore(prop)
        made += 1
    return made


register(
    Stage(name="property_lifecycle", run=_run, depends_on=("bookings",)),
)
