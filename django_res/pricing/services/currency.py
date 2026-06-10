from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist

from core.exceptions import NoRateAvailable
from pricing.models import Currency, FxRate, RatePlan


def default_currency() -> Currency | None:
    """The system default currency — EUR, resolved by code.

    Mirrors legacy `VillaCurrency.IsDefault`. Never `Currency.objects.first()`,
    which is ordering-dependent (GAP-014). Returns `None` only when no EUR row
    exists (an unseeded/degenerate database).
    """
    return Currency.objects.filter(code="EUR").first()


def resolve_property_currency(property: Any) -> Currency | None:
    """Canonical currency resolution for a property (GAP-014).

    1. the property's rate plans — most recent `effective_from` wins (after a
       currency switch this is the villa's *current* currency);
    2. else the `PropertySettings.effective("currency")` chain (property,
       falling back to its group);
    3. else EUR via `default_currency()`.

    Shared by the pricing engine's projection seam, the data-migration
    loaders, and manual quotation lines so the fallback can never drift.
    """
    plan = (
        RatePlan.objects.filter(property=property, is_active=True)
        .order_by("-effective_from", "-pk")
        .select_related("currency")
        .first()
    )
    if plan is not None:
        return plan.currency
    try:
        settings_currency = property.settings.effective("currency")
    except ObjectDoesNotExist:
        # No PropertySettings row — consult the group chain directly.
        try:
            settings_currency = property.group.settings.currency
        except ObjectDoesNotExist:
            settings_currency = None
    if settings_currency is not None:
        return settings_currency
    return default_currency()


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
