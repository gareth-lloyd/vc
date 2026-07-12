"""Pricing background tasks.

`rebuild_summary` is a plain function (directly callable from the shell
and tests); `rebuild_summary_task` is its Celery entry point, enqueued by
the pricing signal handlers via `transaction.on_commit`.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from celery import shared_task
from django.utils import timezone

from pricing.models import RateBand, VillaPricingSummary


@shared_task
def rebuild_summary_task(property_id: int, currency_id: int) -> None:
    """Celery wrapper so signal handlers enqueue instead of recomputing
    inline. Idempotent — a burst of edits enqueuing N rebuilds converges
    on the same row state, just with some wasted work."""
    rebuild_summary(property_id=property_id, currency_id=currency_id)


def rebuild_summary(property_id: int, currency_id: int) -> VillaPricingSummary:
    """Recompute the per-(property, currency) min/max display row."""
    # Lazy-import to avoid circulars during app loading.
    from pricing.models import Currency, RatePlan  # noqa: F401

    # GAP-056: the display min/max mirrors what the engine prices — approved
    # bands on an active period of an active plan. Period activeness is the sole
    # gate now (RateCard is gone).
    rules = RateBand.objects.filter(
        period__plan__property_id=property_id,
        period__plan__currency_id=currency_id,
        period__plan__is_active=True,
        period__is_active=True,
        is_approved=True,
    )

    # Q-018: display truth is the effective (reduced) price — what the engine
    # actually quotes — never the stored base.
    nightlies = [r.effective_nightly for r in rules if r.effective_nightly is not None]
    weeklies = [r.effective_weekly for r in rules if r.effective_weekly is not None]
    parties_min = [int(r.min_party) for r in rules]
    parties_max = [int(r.max_party) for r in rules]

    defaults: dict[str, Any] = {
        "min_nightly": min(nightlies) if nightlies else None,
        "max_nightly": max(nightlies) if nightlies else None,
        "min_weekly": min(weeklies) if weeklies else None,
        "max_weekly": max(weeklies) if weeklies else None,
        "min_party": min(parties_min) if parties_min else 1,
        "max_party": max(parties_max) if parties_max else 1,
        # next_available_date is refreshed by a separate nightly beat task
        # because it depends on Booking + BookingHold state.
        "next_available_date": _next_available_date_placeholder(property_id),
        "rebuilt_at": timezone.now(),
    }

    obj, _ = VillaPricingSummary.objects.update_or_create(
        property_id=property_id,
        currency_id=currency_id,
        defaults=defaults,
    )
    return obj


def _next_available_date_placeholder(property_id: int) -> date | None:
    """Stub: real implementation requires Booking + BookingHold queries."""
    # TODO: query reservations.Booking + reservations.BookingHold once available.
    return None


def refresh_fx() -> None:
    """Pull the latest FX rates from the upstream provider.

    TODO: wire an FX provider (e.g. ECB / Open Exchange Rates). For now this
    is a no-op stub so the Celery beat schedule has a target.
    """
    return None
