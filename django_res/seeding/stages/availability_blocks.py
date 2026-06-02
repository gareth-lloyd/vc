"""Seed a sparse set of operator-editable availability blocks.

Most properties stay completely open so the rest of the system can be
exercised against bookable calendars. A fraction of active properties pick
up 1-N short blocks (owner_block / maintenance / manual) placed in the
future inside the same window bookings spread over. Each block goes
through `HoldService.place`, so overlap with an existing booking or hold
is rejected and silently skipped — the loop just tries the next slot.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from core.exceptions import HoldUnavailable
from reservations.enums import BookingHoldReason
from seeding.context import SeedContext
from seeding.registry import Stage, register

_BLOCK_REASON_WEIGHTS = (
    (BookingHoldReason.OWNER_BLOCK.value, 0.5),
    (BookingHoldReason.MAINTENANCE.value, 0.3),
    (BookingHoldReason.MANUAL.value, 0.2),
)

# Operator blocks are open-ended by nature; mirror the views layer default.
_BLOCK_EXPIRY = timedelta(days=365 * 10)


def _pick_reason(rng: Any) -> str:
    roll = rng.random()
    cumulative = 0.0
    for reason, weight in _BLOCK_REASON_WEIGHTS:
        cumulative += weight
        if roll < cumulative:
            return reason
    return _BLOCK_REASON_WEIGHTS[-1][0]


def _run(ctx: SeedContext) -> int:
    if not ctx.properties:
        return 0
    pct = ctx.knobs.pct_properties_with_blocks
    n_min, n_max = ctx.knobs.blocks_per_property
    len_min, len_max = ctx.knobs.block_length_days
    if pct <= 0 or n_max <= 0 or len_max <= 0:
        return 0

    from reservations.services.holds import HoldService

    active = [p for p in ctx.properties if getattr(p, "status", "active") == "active"]
    if not active:
        return 0

    # Spread blocks across the same forward window bookings use, falling
    # back to a reasonable default if the profile has no spread configured.
    spread = ctx.knobs.booking_date_spread_days or 180
    expires_at = timezone.now() + _BLOCK_EXPIRY

    made = 0
    for prop in active:
        if ctx.rng.random() >= pct:
            continue
        n_blocks = ctx.rng.randint(n_min, n_max)
        for _ in range(n_blocks):
            # Clamp to >=1 day; date_from == date_to would violate the
            # bookinghold_date_from_lt_date_to check constraint and crash
            # the run (HoldService surfaces overlap as HoldUnavailable, but
            # constraint violations come through as IntegrityError).
            length = max(1, ctx.rng.randint(len_min, len_max))
            # Bias toward the future so blocks act like upcoming owner stays
            # / maintenance windows rather than historical noise.
            offset = ctx.rng.randint(1, spread)
            date_from = ctx.today + timedelta(days=offset)
            date_to = date_from + timedelta(days=length)
            try:
                HoldService.place(
                    property=prop,
                    date_from=date_from,
                    date_to=date_to,
                    expires_at=expires_at,
                    reason=_pick_reason(ctx.rng),
                    notes="Seeded availability block",
                )
            except HoldUnavailable:
                continue
            made += 1
    return made


register(
    Stage(
        name="availability_blocks",
        run=_run,
        # Run after property_lifecycle so blocks only land on properties
        # that survive the archive/draft pass — placing a hold on a
        # property that's about to be archived is wasted work.
        depends_on=("bookings", "property_lifecycle"),
    ),
)
