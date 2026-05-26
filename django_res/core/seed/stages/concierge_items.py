"""Attach BookingConciergeItem rows to a fraction of confirmed bookings."""

from __future__ import annotations

from decimal import Decimal

from core.seed.context import SeedContext
from core.seed.registry import Stage, register


def _run(ctx: SeedContext) -> int:
    if not ctx.knobs.pct_concierge:
        return 0
    from reservations.enums import BookingStatus, ConciergeStatus, ConciergeTier, ConciergeUnit
    from reservations.models.booking import Booking
    from reservations.models.concierge import BookingConciergeItem

    catalogue = [
        ("Airport transfer", ConciergeUnit.STAY, Decimal("150.00"), ConciergeTier.SIGNATURE),
        ("Daily housekeeping", ConciergeUnit.DAY, Decimal("80.00"), ConciergeTier.SIGNATURE),
        (
            "Private chef dinner",
            ConciergeUnit.EVENT,
            Decimal("400.00"),
            ConciergeTier.QUINTESSENTIAL,
        ),
        ("Yacht charter", ConciergeUnit.DAY, Decimal("1200.00"), ConciergeTier.QUINTESSENTIAL),
        ("Massage in-villa", ConciergeUnit.HOUR, Decimal("90.00"), ConciergeTier.SIGNATURE),
    ]
    eligible = list(
        Booking.objects.filter(
            status__in=(
                BookingStatus.DEPOSIT_PAID.value,
                BookingStatus.BALANCE_PAID.value,
                BookingStatus.CHECKED_IN.value,
                BookingStatus.CHECKED_OUT.value,
            )
        ).values_list("pk", flat=True)
    )
    # Floor at 1 so small runs (a handful of eligible bookings) still exercise
    # the concierge surface — without this `int(3 * 0.30) == 0`.
    target = max(1, int(len(eligible) * ctx.knobs.pct_concierge)) if eligible else 0
    outcome_statuses = (
        ConciergeStatus.REQUESTED.value,
        ConciergeStatus.CONFIRMED.value,
        ConciergeStatus.DELIVERED.value,
        ConciergeStatus.CANCELLED.value,
    )
    made = 0
    chosen = ctx.rng.sample(eligible, k=min(target, len(eligible)))
    for pk in chosen:
        booking = Booking.objects.get(pk=pk)
        for name, unit, price, tier in ctx.rng.sample(catalogue, k=min(2, len(catalogue))):
            BookingConciergeItem.objects.create(
                booking=booking,
                tier=tier.value,
                name=name,
                quantity=2 if unit == ConciergeUnit.DAY else 1,
                unit=unit.value,
                unit_price=price,
                currency=booking.currency,
                status=outcome_statuses[made % len(outcome_statuses)],
            )
            made += 1
    return made


register(Stage(name="concierge_items", run=_run, depends_on=("bookings",)))
