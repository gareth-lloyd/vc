from __future__ import annotations

from datetime import date
from decimal import Decimal

from pricing.enums import ExtraCalc
from pricing.models import Extra


def calc_extra(
    extra: Extra,
    *,
    nights: int,
    party: int,
    rate_subtotal: Decimal,
) -> Decimal:
    """Compute the per-quote contribution of an Extra based on its `calc`."""
    amount = Decimal(extra.amount)
    if extra.calc == ExtraCalc.FIXED_PER_STAY:
        return amount
    if extra.calc == ExtraCalc.FIXED_PER_NIGHT:
        return (amount * nights).quantize(Decimal("0.01"))
    if extra.calc == ExtraCalc.FIXED_PER_PERSON:
        return (amount * party).quantize(Decimal("0.01"))
    if extra.calc == ExtraCalc.FIXED_PER_PERSON_PER_NIGHT:
        return (amount * nights * party).quantize(Decimal("0.01"))
    if extra.calc == ExtraCalc.PERCENT_OF_SUBTOTAL:
        return (rate_subtotal * amount / Decimal(100)).quantize(Decimal("0.01"))
    raise ValueError(f"Unknown Extra.calc: {extra.calc!r}")


def date_ranges_overlap(
    a_from: date,
    a_to: date,
    b_from: date | None,
    b_to: date | None,
) -> bool:
    """True if [a_from, a_to] intersects [b_from, b_to]; null bounds = open-ended."""
    if b_from is not None and a_to < b_from:
        return False
    return not (b_to is not None and a_from > b_to)
