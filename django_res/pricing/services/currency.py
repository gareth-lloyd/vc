from __future__ import annotations

from datetime import date
from decimal import Decimal

from core.exceptions import NoRateAvailable
from pricing.models import Currency, FxRate


class FxConverter:
    """Convert money amounts via the most recent `FxRate` ≤ `as_of`."""

    @classmethod
    def convert(
        cls,
        amount: Decimal,
        from_ccy: Currency,
        to_ccy: Currency,
        as_of: date | None = None,
    ) -> Decimal:
        if from_ccy.pk == to_ccy.pk:
            return amount
        cutoff = as_of or date.today()
        rate = (
            FxRate.objects.filter(base=from_ccy, quote=to_ccy, as_of__lte=cutoff)
            .order_by("-as_of")
            .first()
        )
        if rate is None:
            raise NoRateAvailable(
                f"No FxRate available for {from_ccy.code}->{to_ccy.code} on/before {cutoff}"
            )
        return (amount * rate.rate).quantize(Decimal("0.01"))
