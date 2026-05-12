"""Pricing background tasks.

These run on Celery in production. For now they are plain functions that
the signal handlers call synchronously — a debounced Celery wrapper will
land when Celery infrastructure is wired in (see TODO below).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone

from pricing.models import RateRule, VillaPricingSummary


def rebuild_summary(property_id: int, currency_id: int) -> VillaPricingSummary:
    """Recompute the per-(property, currency) min/max display row.

    TODO: wrap in a debounced Celery task once Celery infrastructure exists.
    The signal currently calls this synchronously; debouncing will collapse
    bursts of RateRule edits into a single rebuild per (property, currency).
    """
    # Lazy-import to avoid circulars during app loading.
    from pricing.models import Currency, RatePlan  # noqa: F401

    rules = RateRule.objects.filter(
        card__plan__property_id=property_id,
        card__plan__currency_id=currency_id,
        card__plan__is_active=True,
        card__is_active=True,
        is_approved=True,
    )

    nightlies = [Decimal(r.nightly) for r in rules if r.nightly is not None]
    weeklies = [Decimal(r.weekly) for r in rules if r.weekly is not None]
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
