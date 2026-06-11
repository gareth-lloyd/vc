"""Build the transactional graph: Enquiry -> Quotation -> Booking, then walk
each booking a step down its state machine for status variety.

Two layouts share one per-stay builder (`create_one_booking`):

* **Legacy round-robin** (`dense_calendar=False`, i.e. happy): the budget is
  spread one-at-a-time across properties near today. Byte-for-byte reproduces
  the pre-density seeder so smoke tests stay deterministic.
* **Dense calendar** (`dense_calendar=True`, i.e. mixed / chaos): properties are
  partitioned into density tiers (packed / busy / light / empty) and the budget
  is allocated by tier weight, then laid across the full date window with
  positive gaps. Packed villas get a couple of back-to-back changeover pairs and
  a current-month stay, both forced non-terminal so they render on the calendar.

Repeat-guest pool is initialised here on first call so later stages
(`extra_quotations`, `orphan_enquiries`, `notes`, …) can reuse it via
`ctx.guest_pool`.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from django.utils import timezone

from reservations.factories import GuestFactory
from seeding._booking_helpers import conforming_stay, create_one_booking, next_stay_start
from seeding.context import SeedContext
from seeding.registry import Stage, register

# Share of the active portfolio assigned to each density tier. EMPTY villas get
# no stays — they read as new/unlisted and double as candidates for the
# property_lifecycle (draft/archive) pass. `light` is intentionally absent: it
# is the remainder after packed/busy/empty are carved out (see _partition_tiers),
# and it carries a budget weight in _TIER_WEIGHT below.
_TIER_SHARES: dict[str, float] = {"packed": 0.15, "busy": 0.25, "empty": 0.25}
# Relative pull on the booking budget per stay-bearing property (light included).
_TIER_WEIGHT: dict[str, int] = {"packed": 6, "busy": 3, "light": 1}
_STAY_BEARING_TIERS = ("packed", "busy", "light")


def _init_guest_pool(ctx: SeedContext) -> None:
    """One-shot init of the repeat-guest pool the first time bookings runs."""
    if ctx.guest_pool:
        return
    for _ in range(ctx.knobs.repeat_guest_pool_size):
        ctx.guest_pool.append(GuestFactory())


def _terms_for(prop: Any, ctx: SeedContext) -> Any:
    """Pick the currently-published TermsVersion. The seeder always wants a
    single canonical row for the booking it's opening, so the v2 multi-row
    setup picks the current one."""
    return ctx.terms[0]


def _run(ctx: SeedContext) -> int:
    if not ctx.properties:
        return 0
    _init_guest_pool(ctx)
    if ctx.knobs.dense_calendar:
        return _run_dense(ctx)
    return _run_legacy(ctx)


def _run_legacy(ctx: SeedContext) -> int:
    active_properties = [p for p in ctx.properties if p.status == "active"] or ctx.properties
    expires_at = timezone.now() + timedelta(days=7)
    cursors: dict[int, date] = {}
    made = 0
    for i in range(ctx.n_bookings):
        prop = active_properties[i % len(active_properties)]
        # No-op for happy (the stay-rules map is empty); on constrained villas
        # it aligns the start onto the changeover weekday before booking.
        date_from, date_to = conforming_stay(ctx, prop, next_stay_start(prop, cursors, ctx), 7)
        cursors[prop.pk] = date_to + timedelta(days=7)
        create_one_booking(
            ctx,
            prop,
            date_from=date_from,
            date_to=date_to,
            i=i,
            terms=_terms_for(prop, ctx),
            expires_at=expires_at,
        )
        made += 1
    return made


def _run_dense(ctx: SeedContext) -> int:
    active = [p for p in ctx.properties if p.status == "active"] or ctx.properties
    # Longer hold expiry than the legacy 7 days so quotation cells stay live
    # across the demo window.
    expires_at = timezone.now() + timedelta(days=30)
    spread = ctx.knobs.booking_date_spread_days or 180

    tiers = _partition_tiers(active, ctx.rng)
    counts = _allocate_stays(tiers, ctx.n_bookings)

    made = 0
    i = 0  # global counter so advance_status keeps its modulo status variety
    for tier in _STAY_BEARING_TIERS:
        for prop in tiers[tier]:
            count = counts.get(prop.pk, 0)
            if count <= 0:
                continue
            terms = _terms_for(prop, ctx)
            stay_rule = ctx.property_stay_rules.get(prop.pk, (None, 1))
            for stay in _stay_plan(
                count,
                spread,
                ctx.rng,
                packed=(tier == "packed"),
                stay_rule=stay_rule,
                today=ctx.today,
            ):
                create_one_booking(
                    ctx,
                    prop,
                    date_from=ctx.today + timedelta(days=stay["from_off"]),
                    date_to=ctx.today + timedelta(days=stay["to_off"]),
                    i=i,
                    terms=terms,
                    expires_at=expires_at,
                    force_occupying=stay["force"],
                )
                made += 1
                i += 1
    return made


def _partition_tiers(props: list[Any], rng: Any) -> dict[str, list[Any]]:
    """Split the active portfolio into density tiers deterministically.

    Floors: ≥2 empty villas (so property_lifecycle always has candidates) and
    ≥1 packed villa (so the "busy villa" always exists) whenever any stays are
    produced. Light mops up the remainder.

    The empty floor never eats the last stay-bearing villa: it is capped at
    `n - 1` so a tiny portfolio (e.g. `--properties 2`) still books — otherwise
    `stay_bearing` hits 0 and `--bookings` is silently ignored.
    """
    shuffled = list(props)
    rng.shuffle(shuffled)
    n = len(shuffled)
    out: dict[str, list[Any]] = {"packed": [], "busy": [], "light": [], "empty": []}
    if n == 0:
        return out

    n_empty = min(max(2, round(n * _TIER_SHARES["empty"])), n - 1) if n >= 2 else 0
    stay_bearing = n - n_empty
    n_packed = min(stay_bearing, max(1, round(n * _TIER_SHARES["packed"]))) if stay_bearing else 0
    n_busy = min(stay_bearing - n_packed, round(n * _TIER_SHARES["busy"])) if stay_bearing else 0
    n_light = stay_bearing - n_packed - n_busy

    idx = 0
    for tier, size in (
        ("packed", n_packed),
        ("busy", n_busy),
        ("light", n_light),
        ("empty", n_empty),
    ):
        out[tier] = shuffled[idx : idx + size]
        idx += size
    return out


def _allocate_stays(tiers: dict[str, list[Any]], budget: int) -> dict[int, int]:
    """Distribute exactly `budget` stays across the stay-bearing properties by
    tier weight (largest-remainder method).

    Honours `--bookings` exactly: heavier tiers take the integer floor of their
    proportional share and the leftover goes to the largest fractional parts.
    When the budget is smaller than the property count, the lightest villas
    simply get 0 — the budget is never inflated to give everyone a stay.
    """
    weighted: list[tuple[Any, int]] = [
        (prop, _TIER_WEIGHT[tier]) for tier in _STAY_BEARING_TIERS for prop in tiers[tier]
    ]
    total_w = sum(w for _, w in weighted)
    if total_w == 0 or budget <= 0:
        return {}

    raw = {prop.pk: budget * w / total_w for prop, w in weighted}
    counts = {pk: math.floor(share) for pk, share in raw.items()}
    leftover = budget - sum(counts.values())
    # Hand the leftover to the largest fractional parts (ties broken by the
    # larger raw share, then stable weighted order) for a deterministic split.
    order = sorted(raw, key=lambda pk: (raw[pk] - math.floor(raw[pk]), raw[pk]), reverse=True)
    for pk in order[:leftover]:
        counts[pk] += 1
    return counts


def _stay_plan(
    count: int,
    spread: int,
    rng: Any,
    *,
    packed: bool,
    stay_rule: tuple[int | None, int] = (None, 1),
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Lay `count` non-overlapping stays across [today-spread, today+spread].

    Each stay lives in its own equal-width bucket with ≥2-day gaps, so holds and
    the no-overlap booking constraint never collide. The bucket straddling today
    is biased positive and forced non-terminal so the default-open current month
    is populated. Packed villas additionally get 1-2 back-to-back changeover
    pairs (the second stay snapped onto the first's check-out day), both members
    forced non-terminal so the AM/PM changeover day survives.

    On a constrained villa (`stay_rule` carries a required weekday) every stay
    is exactly `min_nights` nights starting on the first occurrence of that
    weekday inside its bucket — no random slack, because aligning *after*
    adding slack could push a checkout into the next bucket and collide holds.
    The alignment costs ≤6 days, so with the bucket floor raised to 16 the
    next bucket keeps a ≥3-day gap (the k0 bucket may abut its successor
    back-to-back, which is harmless: both stays start on the same weekday).
    """
    if count <= 0:
        return []
    weekday, min_nights = stay_rule
    window = 2 * spread
    bucket = max(16 if weekday is not None else 12, window // count)
    k0 = max(0, min(count - 1, round(spread / bucket)))  # bucket containing today
    stays: list[dict[str, Any]] = []
    for k in range(count):
        base = -spread + k * bucket
        if weekday is not None:
            assert today is not None
            nights = min_nights
            lo = max(base, 1) if k == k0 else base
            start = lo + (weekday - (today.weekday() + lo)) % 7
            force = k == k0
        else:
            nights = rng.randint(5, 9)
            slack = max(0, bucket - nights - 2)
            if k == k0:
                lo, hi = max(base, 1), base + slack
                start = rng.randint(lo, hi) if lo <= hi else base
                force = True
            else:
                start = base + (rng.randint(0, slack) if slack else 0)
                force = False
        stays.append(
            {"from_off": start, "to_off": start + nights, "nights": nights, "force": force}
        )

    if packed and count >= 2:
        _add_changeover_pairs(stays, rng, count, k0)
    return stays


def _add_changeover_pairs(stays: list[dict[str, Any]], rng: Any, count: int, k0: int) -> None:
    """Snap a stay onto its predecessor's check-out day to form a changeover
    pair. The right member only ever moves left into the gap, so downstream
    stays never collide. The current-month stay (`k0`) is left untouched."""
    n_pairs = 2 if count >= 6 else 1
    candidates = list(range(count - 1))
    rng.shuffle(candidates)
    # Prefer pairs whose left member is today-or-later: the forced non-terminal
    # changeover never pays a deposit (it stays AWAITING_DEPOSIT), which only
    # reads correctly for a future stay. Stable-sort after the shuffle keeps the
    # pick deterministic; past buckets are a fallback when no future pair exists.
    candidates.sort(key=lambda j: stays[j]["from_off"] < 0)
    used: set[int] = set()
    placed = 0
    for j in candidates:
        if placed >= n_pairs:
            break
        if j in used or (j + 1) in used or j == k0 or (j + 1) == k0:
            continue
        prev, nxt = stays[j], stays[j + 1]
        nxt["from_off"] = prev["to_off"]
        nxt["to_off"] = nxt["from_off"] + nxt["nights"]
        prev["force"] = nxt["force"] = True
        used.update({j, j + 1})
        placed += 1


register(Stage(name="bookings", run=_run, depends_on=("properties",)))
