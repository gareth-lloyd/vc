from __future__ import annotations

from collections.abc import Sequence
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


def settings_currency(property: Any) -> Currency | None:
    """The `PropertySettings.effective("currency")` chain, tolerant of a
    property with no settings row (falls to the group's settings)."""
    try:
        return property.settings.effective("currency")
    except ObjectDoesNotExist:
        try:
            return property.group.settings.currency
        except ObjectDoesNotExist:
            return None


def pick_preferred_plan(plans: Sequence[RatePlan], property: Any) -> RatePlan | None:
    """Canonical multi-currency plan pick (GAP-014).

    `plans` must already be ordered by `-effective_from, -pk`. The most recent
    `effective_from` wins; when same-day plans disagree on currency (18
    overlapping pairs in the whole legacy table), the settings-chain currency
    is preferred, else the newest row.
    """
    if not plans:
        return None
    top = plans[0]
    tied = [p for p in plans if p.effective_from == top.effective_from]
    if len({p.currency_id for p in tied}) > 1:
        preferred = settings_currency(property)
        if preferred is not None:
            for plan in tied:
                if plan.currency_id == preferred.pk:
                    return plan
    return top


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
    plans = list(
        RatePlan.objects.filter(property=property, is_active=True)
        .order_by("-effective_from", "-pk")
        .select_related("currency")
    )
    plan = pick_preferred_plan(plans, property)
    if plan is not None:
        return plan.currency
    configured = settings_currency(property)
    if configured is not None:
        return configured
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
