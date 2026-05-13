from __future__ import annotations

from decimal import Decimal

from pricing.enums import DiscountKind
from pricing.models import Discount


def apply_discount(
    discount: Discount,
    *,
    subtotal: Decimal,
) -> Decimal:
    """Return the discount value to subtract from the subtotal."""
    if discount.kind == DiscountKind.PERCENT:
        return (subtotal * Decimal(discount.amount) / Decimal(100)).quantize(Decimal("0.01"))
    if discount.kind == DiscountKind.FIXED:
        return Decimal(discount.amount).quantize(Decimal("0.01"))
    raise ValueError(f"Unknown Discount.kind: {discount.kind!r}")
