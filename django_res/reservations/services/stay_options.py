"""Stay-option search for the quote builder (`POST /quotations:search-options`).

For each requested property the service prices one stay and reports the
changeover-to-changeover blocks the operator could offer instead:

- No fixed changeover day → a single option: the client's preferred dates.
- Fixed changeover day → candidate blocks are whole weeks (multiples of
  7 nights, nearest the requested length) arriving on the changeover weekday
  inside the flexibility window `preferred ± flex_days`. The block closest to
  the preferred arrival is the default and the only one priced; the frontend
  reprices alternatives on pick via the same endpoint with `flex_days=0`.

Availability flags are advisory snapshots from the same half-open `[from, to)`
overlap predicates the calendar uses. Quoting never blocks availability —
the transactional `HoldUnavailable` guard fires when the operator holds the
line (`QuotationService.hold_line`) or converts it to a booking.

This lives in the reservations layer because pricing may not import the
availability models (spine: reservations > pricing > properties).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.core.exceptions import ObjectDoesNotExist

from core.exceptions import DomainError
from pricing.models import Currency
from pricing.services import PricingContext, PricingEngine
from pricing.services.currency import resolve_property_currency
from properties.models import Property
from properties.services.changeover import ChangeoverService
from reservations.models import Booking, BookingHold

# An occupied interval, half-open: [date_from, date_to).
_Interval = tuple[date, date]


def block_nights(
    requested_nights: int,
    window_nights: int,
    *,
    min_nights: int | None = None,
    max_nights: int | None = None,
) -> int | None:
    """Pick the changeover-block length: the multiple of 7 nights nearest the
    requested stay that fits the window and the plan's card bounds.

    Never a non-multiple — blocks must stay changeover-to-changeover. Returns
    ``None`` when no multiple qualifies; the caller falls back to pricing the
    preferred dates as-is.
    """
    candidates = [
        n
        for n in range(7, window_nights + 1, 7)
        if (min_nights is None or n >= min_nights) and (max_nights is None or n <= max_nights)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda n: (abs(n - requested_nights), n))


def candidate_blocks(
    window_from: date,
    window_to: date,
    weekday: int,
    nights: int,
) -> list[_Interval]:
    """Every `nights`-long block arriving on `weekday` that fits the window."""
    blocks: list[_Interval] = []
    arrival = window_from
    last_arrival = window_to - timedelta(days=nights)
    while arrival <= last_arrival:
        if arrival.weekday() == weekday:
            blocks.append((arrival, arrival + timedelta(days=nights)))
        arrival += timedelta(days=1)
    return blocks


def pick_default(blocks: list[_Interval], preferred_from: date) -> int:
    """Index of the block whose arrival is closest to the preferred one
    (tie → the earlier arrival)."""
    return min(
        range(len(blocks)),
        key=lambda i: (abs((blocks[i][0] - preferred_from).days), blocks[i][0]),
    )


class StayOptionsService:
    @classmethod
    def search(
        cls,
        *,
        requests: list[dict[str, Any]],
        flex_days: int,
        currency: Currency | None = None,
    ) -> list[dict[str, Any]]:
        """Price one stay per request entry and attach its `stay_options`.

        Entries are validated dicts: property_id, date_from, date_to, adults,
        children. The result rows mirror `/pricing:quote-bulk` (flattened
        breakdown / Q-013 error shape) plus `stay_options`.
        """
        property_ids = [entry["property_id"] for entry in requests]
        properties_by_id = {
            p.pk: p
            for p in Property.objects.filter(pk__in=property_ids)
            # `settings` feeds the engine's villa min-nights
            # default (GAP-056); fold them into this fetch so the per-property
            # resolution costs no extra query.
            .select_related("settings")
            .prefetch_related("images")
        }
        occupied = cls._occupied_intervals(requests, flex_days)
        return [
            cls._search_one(
                entry,
                flex_days=flex_days,
                currency=currency,
                properties_by_id=properties_by_id,
                occupied=occupied,
            )
            for entry in requests
        ]

    @classmethod
    def weekly_prices(
        cls,
        *,
        property_ids: list[int],
        window_from: date,
        window_to: date,
        currency: Currency | None = None,
    ) -> list[dict[str, Any]]:
        """Per-changeover-week guide prices for the multi-villa timeline (GAP-030).

        For each **fixed-changeover** property, price every changeover-anchored
        7-night block intersecting ``[window_from, window_to)`` at base occupancy
        (`PropertyCapacity.guests`). **Flexible** (`any`) changeover villas are
        deferred (cross-ref GAP-025 / Q-022): they return ``changeover_day=None``
        and no weeks — the caller renders no strip, never an error.

        A week with no automatic price (no covering rate, POA, or party out of
        range) yields ``price=None`` plus the Q-013 incomplete-pricing shape —
        never a 500 — mirroring `_search_one`. Guide (projected) prices carry
        ``is_projected=True``.

        Performance: ONE `PricingEngine.load_context()` per property covers the
        whole window when a single plan spans it, and every week's quote reuses
        it — no per-week plan/card/rule reload. When a plan boundary falls
        inside the window the load returns ``None`` and each week loads its own
        context (still correct, just off the fast path).
        """
        properties_by_id = {
            p.pk: p
            for p in Property.objects.filter(pk__in=property_ids)
            # `settings` feeds the engine's villa min-nights
            # default (GAP-056) that every per-week `quote()` now resolves; fold
            # them in so the timeline doesn't re-query settings per property.
            .select_related("capacity", "settings")
        }
        return [
            cls._weekly_prices_one(
                properties_by_id.get(property_id),
                property_id,
                window_from=window_from,
                window_to=window_to,
                currency=currency,
            )
            for property_id in property_ids
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @classmethod
    def _search_one(
        cls,
        entry: dict[str, Any],
        *,
        flex_days: int,
        currency: Currency | None,
        properties_by_id: dict[int, Property],
        occupied: dict[int, list[_Interval]],
    ) -> dict[str, Any]:
        property_obj = properties_by_id.get(entry["property_id"])
        if property_obj is None:
            return {"property_id": entry["property_id"], "available": False}

        preferred_from: date = entry["date_from"]
        preferred_to: date = entry["date_to"]
        blocks, default_index, context = cls._plan_blocks(
            property_obj,
            preferred_from=preferred_from,
            preferred_to=preferred_to,
            flex_days=flex_days,
            currency=currency,
        )
        price_from, price_to = blocks[default_index] if blocks else (preferred_from, preferred_to)

        # GAP-044 occupancy fan-out: enumerate + price every covering band for
        # the default block, independent of the searched party (B2). Computed
        # before the headline quote so an out-of-bracket / POA search — which
        # fails below — still returns the bands the builder fans out.
        occupancy_bands = cls._occupancy_bands(
            property_obj, price_from, price_to, currency=currency, context=context
        )

        try:
            quote = PricingEngine.quote(
                property=property_obj,
                date_from=price_from,
                date_to=price_to,
                party=entry["adults"] + entry.get("children", 0),
                currency=currency,
                # The window context from block planning (covers any priced
                # stay inside it) — None falls back to the engine's own load.
                context=context,
            )
        except DomainError as exc:
            # Q-013 parity with /pricing:quote-bulk — no-rate entries feed the
            # manual-quote card, so they alone resolve a display currency.
            code = getattr(exc, "code", "domain_error")
            resolved = (
                resolve_property_currency(property_obj) if code == "no_rate_available" else None
            )
            return {
                "property_id": entry["property_id"],
                "available": False,
                "error_code": code,
                "error_detail": str(exc),
                "hero_image_url": property_obj.hero_image_url(),
                "currency_code": resolved.code if resolved else None,
                "occupancy_bands": occupancy_bands,
            }

        if blocks:
            # The engine may still have shifted the default arrival (a
            # changeover rule boundary inside the window — v1 resolves the
            # weekday at the preferred arrival only). Keep the default option
            # in lockstep with the dates actually priced.
            blocks[default_index] = (quote.date_from, quote.date_to)
        else:
            blocks = [(quote.date_from, quote.date_to)]
            default_index = 0

        intervals = occupied.get(property_obj.pk, [])
        stay_options = [
            {
                "date_from": block_from.isoformat(),
                "date_to": block_to.isoformat(),
                "nights": (block_to - block_from).days,
                "is_default": index == default_index,
                "is_available": not cls._overlaps_any(block_from, block_to, intervals),
            }
            for index, (block_from, block_to) in enumerate(blocks)
        ]
        return {
            "property_id": entry["property_id"],
            "available": True,
            "hero_image_url": property_obj.hero_image_url(),
            **quote.breakdown,
            "stay_options": stay_options,
            "occupancy_bands": occupancy_bands,
        }

    @classmethod
    def _occupancy_bands(
        cls,
        property_obj: Property,
        date_from: date,
        date_to: date,
        *,
        currency: Currency | None,
        context: PricingContext | None,
    ) -> list[dict[str, Any]]:
        """Every covering occupancy band for the week, each re-priced at its own
        representative party (GAP-044 fan-out).

        The quote builder renders one default-checked line per band, so it needs
        all covering brackets — enumerated independent of the searched party
        (B2): an out-of-bracket or POA search still shows them. Returns ``[]``
        unless the covering card carries **≥2** brackets (a single-band villa
        keeps its one headline line — the threshold lives here, not in the
        party-agnostic enumerator).

        One context load covers the enumeration and every per-band re-price:
        supplied non-None on the fixed-changeover path, else loaded once here
        (B1 — a flexible-changeover villa arrives with ``context=None`` yet may
        be occupancy-priced). Each band prices at ``max(1, min_party)``
        (decision 7 — guards a storable ``min_party=0``); a POA / no-rate band
        is flagged (``total=None``) not dropped (Q-013).
        """
        if context is None:
            context = PricingEngine.load_context(
                property_obj, date_from=date_from, date_to=date_to, currency=currency
            )
        bands = PricingEngine.covering_bands(
            property=property_obj,
            date_from=date_from,
            date_to=date_to,
            currency=currency,
            context=context,
        )
        if len(bands) < 2:
            return []
        # covering_bands only returns bands when a real plan covers the week, so
        # the context it used (loaded above or supplied) is non-None here.
        assert context is not None

        priced: list[dict[str, Any]] = []
        for band in bands:
            party = max(1, band.min_party)
            try:
                quote = PricingEngine.quote(
                    property=property_obj,
                    date_from=date_from,
                    date_to=date_to,
                    party=party,
                    currency=currency,
                    context=context,
                )
            except DomainError as exc:
                # Q-013: POA / no-rate flags the band, never drops it. POA is a
                # NoRateAvailable whose message names it. Its display currency is
                # the covering plan's (or the searched currency) — the very one
                # every priceable band reports, so a POA band can never show a
                # different currency than its siblings in the same fan-out. We
                # take it straight off the shared `context` (guaranteed non-None
                # here — covering_bands returned ≥2 bands, so a plan covers the
                # week), rather than re-resolving the property's *current*
                # currency, which a currency switch could make diverge.
                code = getattr(exc, "code", "domain_error")
                is_poa = code == "no_rate_available" and "POA" in str(exc)
                band_currency = (
                    currency.code if currency is not None else context.plan.currency.code
                )
                priced.append(
                    {
                        "min_party": band.min_party,
                        "max_party": band.max_party,
                        "adults": party,
                        "total": None,
                        "total_before_reduction": None,
                        "currency_code": band_currency if code == "no_rate_available" else None,
                        "is_projected": False,
                        "is_poa": is_poa,
                        "error_code": code,
                    }
                )
                continue
            priced.append(
                {
                    "min_party": band.min_party,
                    "max_party": band.max_party,
                    "adults": party,
                    "total": str(quote.total),
                    # Q-018: null unless a rate reduction changed this band's price.
                    "total_before_reduction": (
                        str(quote.total_before_reduction)
                        if quote.total_before_reduction is not None
                        else None
                    ),
                    "currency_code": quote.currency_code,
                    "is_projected": quote.is_projected,
                    "is_poa": False,
                    "error_code": None,
                }
            )
        return priced

    @classmethod
    def _plan_blocks(
        cls,
        property_obj: Property,
        *,
        preferred_from: date,
        preferred_to: date,
        flex_days: int,
        currency: Currency | None,
    ) -> tuple[list[_Interval], int, PricingContext | None]:
        """Candidate changeover blocks for the window, the default index, and
        the rate context the bounds came from (for the quote to reuse — it
        covers the whole window, so it covers whichever block gets priced).

        Empty list → no fixed changeover day, or no whole-week block fits:
        price the preferred dates as-is (the engine's align-forward is the
        backstop, exactly as before this feature).

        The bounds clamp needs one plan covering the whole window; when only
        the preferred dates are covered (a plan boundary inside the window —
        the same accepted v1 edge as a changeover-rule boundary) the context
        is ``None``, the clamp is skipped, and the engine loads its own
        context and stays the loud guard.
        """
        weekday = ChangeoverService.required_weekday(property_obj, preferred_from)
        if weekday is None:
            return [], 0, None
        window_from = preferred_from - timedelta(days=flex_days)
        window_to = preferred_to + timedelta(days=flex_days)
        context = PricingEngine.load_context(
            property_obj,
            date_from=window_from,
            date_to=window_to,
            currency=currency,
        )
        bounds = PricingEngine.stay_length_bounds(context) if context else None
        nights = block_nights(
            (preferred_to - preferred_from).days,
            (preferred_to - preferred_from).days + 2 * flex_days,
            min_nights=bounds[0] if bounds else None,
            max_nights=bounds[1] if bounds else None,
        )
        if nights is None:
            return [], 0, context
        blocks = candidate_blocks(window_from, window_to, weekday, nights)
        if not blocks:
            return [], 0, context
        return blocks, pick_default(blocks, preferred_from), context

    @classmethod
    def _weekly_prices_one(
        cls,
        property_obj: Property | None,
        property_id: int,
        *,
        window_from: date,
        window_to: date,
        currency: Currency | None,
    ) -> dict[str, Any]:
        if property_obj is None:
            return {"property_id": property_id, "changeover_day": None, "weeks": []}
        # Surface the changeover as the code string ("sat") the rest of the
        # quote API already uses, not a raw weekday int.
        day_code = ChangeoverService.effective_day(property_obj, window_from)
        weekday = ChangeoverService.weekday_for(day_code)
        if weekday is None:
            # Flexible / ANY changeover — deferred (GAP-025, Q-022).
            return {"property_id": property_id, "changeover_day": None, "weeks": []}
        blocks = candidate_blocks(window_from, window_to, weekday, 7)
        party = cls._guide_party(property_obj)
        # One context for the whole window — reused by every week's quote when a
        # single plan spans it (see the method docstring's performance note).
        window_context = PricingEngine.load_context(
            property_obj,
            date_from=window_from,
            date_to=window_to,
            currency=currency,
        )
        weeks = [
            cls._price_week(
                property_obj,
                week_from,
                week_to,
                party=party,
                currency=currency,
                window_context=window_context,
            )
            for week_from, week_to in blocks
        ]
        return {"property_id": property_id, "changeover_day": day_code, "weeks": weeks}

    @staticmethod
    def _guide_party(property_obj: Property) -> int:
        """Base occupancy for the guide price; never below 1 (an occupancy-
        bracketed plan would 400 on party=0, so floor it and let the quote
        raise loudly only on a genuine out-of-range)."""
        try:
            guests = property_obj.capacity.guests
        except ObjectDoesNotExist:
            guests = 0
        return max(guests or 0, 1)

    @classmethod
    def _price_week(
        cls,
        property_obj: Property,
        week_from: date,
        week_to: date,
        *,
        party: int,
        currency: Currency | None,
        window_context: PricingContext | None,
    ) -> dict[str, Any]:
        try:
            quote = PricingEngine.quote(
                property=property_obj,
                date_from=week_from,
                date_to=week_to,
                party=party,
                currency=currency,
                # The window context (covers any week inside it) — None falls
                # back to the engine's own per-week load / projection.
                context=window_context,
            )
        except DomainError as exc:
            # Q-013 parity: no-rate / POA / party-out-of-range feed the
            # incomplete-pricing shape, never a 500. POA is a NoRateAvailable
            # whose message names it (the engine has no distinct POA code).
            code = getattr(exc, "code", "domain_error")
            is_poa = code == "no_rate_available" and "POA" in str(exc)
            resolved = (
                resolve_property_currency(property_obj) if code == "no_rate_available" else None
            )
            return {
                "week_start": week_from.isoformat(),
                "week_end": week_to.isoformat(),
                "price": None,
                "total_before_reduction": None,
                "currency_code": resolved.code if resolved else None,
                "is_projected": False,
                "is_poa": is_poa,
                "error_code": code,
            }
        return {
            "week_start": week_from.isoformat(),
            "week_end": week_to.isoformat(),
            "price": str(quote.total),
            # Q-018: null unless a rate reduction changed this week's price.
            "total_before_reduction": (
                str(quote.total_before_reduction)
                if quote.total_before_reduction is not None
                else None
            ),
            "currency_code": quote.currency_code,
            "is_projected": quote.is_projected,
            "is_poa": False,
            "error_code": None,
        }

    @staticmethod
    def _occupied_intervals(
        requests: list[dict[str, Any]],
        flex_days: int,
    ) -> dict[int, list[_Interval]]:
        """ONE batched fetch of every booking/hold interval that could touch
        any request's flexibility window, keyed by property id."""
        if not requests:
            return {}
        property_ids = {entry["property_id"] for entry in requests}
        global_from = min(entry["date_from"] for entry in requests) - timedelta(days=flex_days)
        global_to = max(entry["date_to"] for entry in requests) + timedelta(days=flex_days)
        occupied: dict[int, list[_Interval]] = {}
        rows = Booking.objects.occupying(date_from=global_from, date_to=global_to).filter(
            property_id__in=property_ids
        )
        for property_id, date_from, date_to in rows.values_list(
            "property_id", "date_from", "date_to"
        ):
            occupied.setdefault(property_id, []).append((date_from, date_to))
        holds = BookingHold.live_overlapping(date_from=global_from, date_to=global_to).filter(
            property_id__in=property_ids
        )
        for property_id, date_from, date_to in holds.values_list(
            "property_id", "date_from", "date_to"
        ):
            occupied.setdefault(property_id, []).append((date_from, date_to))
        return occupied

    @staticmethod
    def _overlaps_any(date_from: date, date_to: date, intervals: list[_Interval]) -> bool:
        # Half-open [from, to): arriving the day another stay departs is fine.
        return any(
            date_from < other_to and date_to > other_from for other_from, other_to in intervals
        )
