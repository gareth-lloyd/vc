from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q, Subquery
from django.utils import timezone

from core.exceptions import NoRateAvailable
from pricing.models import Currency, FxRate, RatePeriod, RatePlan


def quantise_money(amount: Decimal, currency: Currency) -> Decimal:
    """Round `amount` to `currency.decimal_places` (SMELL-003).

    The single chokepoint that makes money amounts honour their currency's
    minor-unit precision before they are persisted: a JPY (0 dp) amount loses
    any cents, a BHD (3 dp) amount keeps its third place. Uses Decimal's
    default rounding (ROUND_HALF_EVEN), matching the hand-rolled
    `.quantize(Decimal("0.01"))` calls scattered through the pricing/payments
    services. Service write paths call this on every money field that carries
    a currency.
    """
    quantum = Decimal(10) ** -currency.decimal_places
    return amount.quantize(quantum)


def default_currency() -> Currency | None:
    """The system default currency — EUR, resolved by code.

    Mirrors legacy `VillaCurrency.IsDefault`. Never `Currency.objects.first()`,
    which is ordering-dependent (GAP-014). Returns `None` only when no EUR row
    exists (an unseeded/degenerate database).
    """
    return Currency.objects.filter(code="EUR").first()


def settings_currency(property: Any) -> Currency | None:
    """`PropertySettings.currency`, tolerant of a property with no settings
    row. Stays nullable — there is no runtime currency fallback (GAP-070)."""
    try:
        return property.settings.currency
    except ObjectDoesNotExist:
        return None


def pick_preferred_plan(plans: Sequence[RatePlan], property: Any) -> RatePlan | None:
    """Canonical multi-currency plan pick (GAP-014, regime model per GAP-110).

    Among candidate plans that are all equally eligible on dates (the caller
    has already applied its period-based rule), the settings-chain currency
    is preferred, else the lowest plan pk — deterministic and independent of
    which row was written last. `RatePlan` carries no dates, so there is no
    recency to break ties on.
    """
    if not plans:
        return None
    ordered = sorted(plans, key=lambda p: p.pk)
    if len({p.currency_id for p in ordered}) > 1:
        # Only pay the settings lookup when currencies actually disagree.
        preferred = settings_currency(property)
        if preferred is not None:
            for plan in ordered:
                if plan.currency_id == preferred.pk:
                    return plan
    return ordered[0]


def resolve_property_currency(property: Any) -> Currency | None:
    """Canonical currency resolution for a property (GAP-014, GAP-110).

    1. the currency of the active plan with an active period covering today
       (after a currency switch this is the villa's *current* currency; a
       pre-loaded future period — a scheduled switch — must not dictate
       today's currency);
    2. else the plan owning the latest period that ended before today;
    3. else the property's own `PropertySettings.currency`;
    4. else the plan owning the earliest period still to come (a villa whose
       only rates are upcoming, with no settings currency — a far better
       guess than the system default);
    5. else EUR via `default_currency()`.

    Ties between currencies at steps 1, 2 and 4 go to `pick_preferred_plan`
    (settings currency, then lowest plan pk). Shared by the pricing engine's
    projection seam, the data-migration loaders, and manual quotation lines
    so the fallback can never drift.
    """
    today = timezone.localdate()
    live = RatePeriod.objects.filter(
        property=property, is_active=True, plan__is_active=True
    ).select_related("plan__currency")
    elapsed = live.filter(date_to__lt=today)
    # One query: the periods covering today, else those sharing the latest
    # elapsed end date (at most one per currency either way).
    periods = list(
        live.filter(
            Q(date_from__lte=today, date_to__gte=today)
            | Q(date_to=Subquery(elapsed.order_by("-date_to").values("date_to")[:1]))
        )
    )
    if any(period.date_to >= today for period in periods):
        periods = [period for period in periods if period.date_to >= today]
    plan = pick_preferred_plan([period.plan for period in periods], property)
    if plan is not None:
        return plan.currency
    configured = settings_currency(property)
    if configured is not None:
        return configured
    upcoming = live.filter(date_from__gt=today)
    periods = list(
        upcoming.filter(date_from=Subquery(upcoming.order_by("date_from").values("date_from")[:1]))
    )
    plan = pick_preferred_plan([period.plan for period in periods], property)
    if plan is not None:
        return plan.currency
    return default_currency()


class FxConverter:
    """Convert money amounts via the most recent `FxRate` ≤ `as_of`."""

    @classmethod
    def lookup_rate(
        cls,
        from_ccy: Currency,
        to_ccy: Currency,
        as_of: date | None = None,
    ) -> FxRate:
        """The `FxRate` row `convert` would apply — exposed for callers that
        need the applied rate itself (e.g. to record conversion provenance)."""
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
        return rate

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
        rate = cls.lookup_rate(from_ccy, to_ccy, as_of)
        return quantise_money(amount * rate.rate, to_ccy)
