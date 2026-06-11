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
            p.pk: p for p in Property.objects.filter(pk__in=property_ids).prefetch_related("images")
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
        }

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
