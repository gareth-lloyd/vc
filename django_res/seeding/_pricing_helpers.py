"""Realistic pricing shapes for seeded villas (mixed / chaos).

Calibrated from the April-2025 legacy snapshot (7,178 live VillaSeasonRate
rows across 304 villas): per-currency log-normal nightly price levels inside
the observed clamps, a Low/Mid/Peak seasonal card structure (legacy villas
average ~24 seasonal rates — three season cards is the KISS rendition),
occupancy-band party brackets on a small fraction of villas, and
near-universal percentage commission.

Shared by the `properties` stage and `dashboard_activity`'s showcase villas
so the whole portfolio prices alike. Kept private to the seed package.
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from pricing.factories import RateCardFactory, RateRuleFactory
from properties.enums import CommissionCalcType

# currency code -> (median nightly, sigma, clamp lo, clamp hi). Nightly =
# legacy weekly / 7; sigma ~= ln(p95 / median) / 1.645 from the snapshot.
_PRICE_SHAPE: dict[str, tuple[int, float, int, int]] = {
    "EUR": (2100, 0.74, 280, 22000),
    "GBP": (1220, 0.79, 170, 19000),
    "USD": (3825, 0.51, 2000, 17800),
}

_SEASONS = ("Low", "Mid", "Peak")
# month -> index into _SEASONS: Peak Jun-Sep, Mid Apr-May + Oct, Low rest.
_MONTH_SEASON = {1: 0, 2: 0, 3: 0, 4: 1, 5: 1, 6: 2, 7: 2, 8: 2, 9: 2, 10: 1, 11: 0, 12: 0}
_SEASON_MULTIPLIERS = (Decimal("0.7"), Decimal("1.0"), Decimal("1.5"))
# A couple of villas per run echo the legacy extreme low/peak ratios.
_WIDE_SEASON_MULTIPLIERS = (Decimal("0.3"), Decimal("1.0"), Decimal("3.0"))

_FLAT_BRACKETS: tuple[tuple[int, int, Decimal], ...] = ((1, 30, Decimal("1.0")),)

# Free-text "what's included" copy in the legacy VillaSeason.Inclusion style
# ("Daily housekeeping, welcome basket"). Cycled by villa index — never the
# rng — so the pool can grow without perturbing the seeded rng stream.
_INCLUSIONS: tuple[str, ...] = (
    "Daily housekeeping, welcome hamper on arrival",
    "Daily maid service, pool heating, mid-stay linen change",
    "Private chef for breakfast and dinner, daily housekeeping",
    "Return airport transfers, daily housekeeping, concierge service",
    "Welcome basket, twice-weekly linen and towel change, end-of-stay clean",
    "Continental breakfast daily, pool and garden maintenance, Wi-Fi",
    "Concierge service, daily housekeeping, all utilities included",
    "Half-board chef service, airport meet-and-greet, daily maid service",
    "Daily housekeeping, cot and high chair on request, welcome groceries",
    "Pool heating (April-October), gardener, daily maid service",
)


def inclusion_for(index: int) -> str:
    """The villa-index slot in the inclusion pool (wraps when exhausted)."""
    return _INCLUSIONS[index % len(_INCLUSIONS)]


def draw_base_nightly(rng: random.Random, currency_code: str) -> Decimal:
    """A villa's base (Mid-season) nightly price: log-normal in the legacy
    per-currency shape, clamped to the observed extremes, rounded to 10s.
    Unknown currencies fall back to the EUR shape (the dominant book)."""
    median, sigma, lo, hi = _PRICE_SHAPE.get(currency_code, _PRICE_SHAPE["EUR"])
    value = rng.lognormvariate(math.log(median), sigma)
    return Decimal(round(min(max(value, lo), hi) / 10) * 10)


def party_brackets(capacity: int) -> tuple[tuple[int, int, Decimal], ...]:
    """Contiguous occupancy brackets partitioning 1..capacity, larger parties
    pricier. The first bracket must start at 1 so the seeder's party of 3
    always matches (the engine raises PartyOutOfRange otherwise)."""
    if capacity <= 12:
        return ((1, 8, Decimal("1.0")), (9, capacity, Decimal("1.15")))
    return ((1, 8, Decimal("1.0")), (9, 12, Decimal("1.15")), (13, capacity, Decimal("1.25")))


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def _season_segments(window_from: date, window_to: date) -> list[tuple[date, date, int]]:
    """Maximal same-season month runs covering `[window_from, window_to]`
    (inclusive on both ends, matching RateRule date semantics), gap-free."""
    segments: list[tuple[date, date, int]] = []
    run_start = window_from
    current = _MONTH_SEASON[window_from.month]
    cursor = _next_month(window_from)
    while cursor <= window_to:
        season = _MONTH_SEASON[cursor.month]
        if season != current:
            segments.append((run_start, cursor - timedelta(days=1), current))
            run_start, current = cursor, season
        cursor = _next_month(cursor)
    segments.append((run_start, window_to, current))
    return segments


def build_seasonal_cards(
    plan: Any,
    base_nightly: Decimal,
    *,
    min_nights: int = 1,
    brackets: tuple[tuple[int, int, Decimal], ...] = _FLAT_BRACKETS,
    wide_spread: bool = False,
) -> None:
    """Three Low/Mid/Peak cards on `plan`, one rule per (season segment x
    party bracket), partitioning the whole plan window gap-free so any stay
    the booking stages generate prices without NoRateAvailable.

    `min_nights` lands on every card: the engine validates it against the
    first night's card only, so all cards must agree. `max_nights` stays null.
    """
    assert plan.effective_to is not None  # factories/stages always set it
    multipliers = _WIDE_SEASON_MULTIPLIERS if wide_spread else _SEASON_MULTIPLIERS
    cards = [
        RateCardFactory(plan=plan, name=name, sort_order=idx, min_nights=min_nights)
        for idx, name in enumerate(_SEASONS)
    ]
    for seg_from, seg_to, season in _season_segments(plan.effective_from, plan.effective_to):
        for min_party, max_party, bracket_mult in brackets:
            RateRuleFactory(
                card=cards[season],
                date_from=seg_from,
                date_to=seg_to,
                min_party=min_party,
                max_party=max_party,
                nightly=(base_nightly * multipliers[season] * bracket_mult).quantize(Decimal("1")),
            )


def assign_commission(rng: random.Random, prop: Any) -> None:
    """Commission terms mirroring legacy: ~97% percentage-based (avg 18.8%,
    max 25%), the rest fixed. Overrides the narrower `with_owner_contact`
    factory values so seeded villas read like the real book."""
    finance = prop.finance
    if rng.random() < 0.97:
        finance.commission_calculation_type = CommissionCalcType.PERCENT.value
        # Uniform 12-25 quantised to 0.5 brackets the legacy avg/max.
        finance.commission_amount = Decimal(rng.randint(24, 50)) / 2
    else:
        finance.commission_calculation_type = CommissionCalcType.FIXED.value
        finance.commission_amount = Decimal(rng.randint(5, 50) * 100)
    finance.save(update_fields=["commission_calculation_type", "commission_amount"])
