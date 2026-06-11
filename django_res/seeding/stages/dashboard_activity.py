"""Guaranteed dashboard activity — today-anchored stays + resting statuses.

The dense calendar spreads stays across ±365 days, which almost never lands an
arrival or departure exactly on today, never *rests* a booking at
AWAITING_BALANCE (the lifecycle walker pays the balance in the same breath as
arming it), and never leaves an enquiry NEW. The staff dashboard reads exactly
those slices, so a freshly seeded DB renders a dead dashboard.

This stage tops the run up with five cohorts (base counts x ctx.dashboard_factor):

* arrivals today    — ``date_from == today``, resting BALANCE_PAID
* departures today  — ``date_to == today``, resting BALANCE_PAID (deliberately
  NOT CHECKED_IN: the daily ``auto_check_out`` beat task sweeps CHECKED_IN
  stays with ``date_to <= today`` into terminal CHECKED_OUT, which would zero
  the "Check-outs today" tile on any beat-running environment within hours)
* awaiting balance  — future stays resting AWAITING_BALANCE
* NEW enquiries     — untouched factory enquiries for the "New enquiries" tile
* owner upcoming    — DEPOSIT_PAID stays in the next 30 days on granted villas

Candidates are searched busy-first so the deliberately-empty density tier is
consumed last; when no existing villa is free for a window, a "showcase" villa
is minted instead — manifest-styled like the properties stage and reused for
later windows — so the guarantee holds at any scale and on additive reruns
(`--properties N` is therefore a floor, not an exact bound). Runs for every
profile; `--no-dashboard-activity` (dashboard_factor == 0) disables.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, cast

import structlog
from django.db import IntegrityError
from django.utils import timezone

from core.exceptions import HoldUnavailable
from payments.enums import PaymentPurpose
from pricing.factories import RateCardFactory, RatePlanFactory, RateRuleFactory
from properties.factories import PropertyFactory, RegionFactory, villa_manifest
from properties.models import Country, Property
from reservations.factories import EnquiryFactory
from reservations.models.booking import Booking, BookingHold
from reservations.models.enquiry import Enquiry
from seeding._booking_helpers import create_one_booking, mark_payment_paid, pick_guest
from seeding.context import SeedContext
from seeding.registry import Stage, register
from seeding.stages.owner_orgs import _ORG_NAME
from seeding.stages.properties import _parse_hhmm

logger = structlog.get_logger(__name__)

# Base cohort sizes at small scale; multiplied by ctx.dashboard_factor.
_ARRIVALS = 5
_DEPARTURES = 3
_AWAITING_BALANCE = 4
_NEW_ENQUIRIES = 5
_UPCOMING = 4
# Today-anchored stays are deliberately short so they slot into the gaps the
# dense layout leaves around today instead of forcing showcase-villa top-ups.
_TODAY_NIGHTS = 3
# Owner-portal "upcoming arrivals" reads the next 30 days; spread the cohort
# across the window. Offset 3 abuts (but never overlaps) the arrivals-today
# stays, which end on today + _TODAY_NIGHTS.
_UPCOMING_OFFSETS = (3, 12, 21)
_UPCOMING_NIGHTS = 6


def _is_free(prop: Any, date_from: date, date_to: date) -> bool:
    """Both canonical occupancy predicates clear for `[date_from, date_to)`."""
    return (
        not Booking.objects.occupying(property=prop, date_from=date_from, date_to=date_to).exists()
        and not BookingHold.live_overlapping(
            property=prop, date_from=date_from, date_to=date_to
        ).exists()
    )


def _requires_pre_approval(prop: Any) -> bool:
    return bool(cast(Any, prop.settings).effective("bookings_require_pre_approval"))


def _candidates(ctx: SeedContext) -> list[Any]:
    """Active, auto-approving villas, shuffled then stable-sorted busy-first.

    Busy-first matters: empty-tier villas are by construction the most likely
    to be free around today, so a naive first-free pick would consume them and
    erase the deliberate density gradient. Statuses are re-read from the DB —
    property_lifecycle may have archived an in-memory instance.
    """
    active_pks = set(
        Property.objects.filter(pk__in=[p.pk for p in ctx.properties], status="active").values_list(
            "pk", flat=True
        )
    )
    candidates = [p for p in ctx.properties if p.pk in active_pks and not _requires_pre_approval(p)]
    ctx.rng.shuffle(candidates)
    booked_pks = set(
        Booking.objects.filter(property__in=candidates).values_list("property_id", flat=True)
    )
    candidates.sort(key=lambda p: p.pk not in booked_pks)
    return candidates


def _new_showcase_property(ctx: SeedContext) -> Any:
    """A fresh bookable villa for when no existing one is free.

    Mirrors the demo-visible essentials of the properties stage — manifest
    villa imagery / region / description, changeover times, and the
    pricing graph — because at small scale minting is the *common* path and
    these villas host the dashboard's hero-tile arrivals. Registered on
    `ctx.properties` so later stages (rooms runs after this one) furnish them
    like any other villa.
    """
    extra_kwargs: dict[str, Any] = {}
    villa_pool = villa_manifest()
    if villa_pool:
        # Continue the properties stage's pool cycle (it seeded one villa per
        # ctx.properties entry), so showcase villas exhaust fresh imagery
        # before any repeats. The name comes from the factory's deterministic
        # villa_name menu, not the manifest.
        villa = villa_pool[len(ctx.properties) % len(villa_pool)]
        country = Country.objects.get(iso2=villa["country_iso2"])
        locality = villa["location_tag"].rsplit(",", 1)[0].strip()
        extra_kwargs["region"] = RegionFactory(country=country, name=locality)
        extra_kwargs["children__villa"] = villa
    prop = cast(Any, PropertyFactory(with_owner_contact=False, **extra_kwargs))
    check_out, check_in = ctx.knobs.changeover_times
    if check_out is not None and check_in is not None:
        prop.settings.check_out_time = _parse_hhmm(check_out)
        prop.settings.check_in_time = _parse_hhmm(check_in)
        prop.settings.save(update_fields=["check_out_time", "check_in_time"])
    plan = RatePlanFactory(property=prop, currency=ctx.default_currency)
    card = RateCardFactory(plan=plan)
    RateRuleFactory(card=card)
    ctx.properties.append(prop)
    return prop


def _open_stay(
    ctx: SeedContext, prop: Any, date_from: date, date_to: date, terms: Any, expires_at: Any
) -> Any:
    """Open one force-occupying booking; None on a (should-be-prevented)
    collision. A failed attempt strands its NEW enquiry — harmless, it feeds
    the "New enquiries" tile."""
    try:
        return create_one_booking(
            ctx,
            prop,
            date_from=date_from,
            date_to=date_to,
            i=0,
            terms=terms,
            expires_at=expires_at,
            force_occupying=True,
        )
    except (HoldUnavailable, IntegrityError):
        return None


def _settle_deposit(booking: Any) -> None:
    booking.record_deposit()
    mark_payment_paid(booking, PaymentPurpose.DEPOSIT.value)


def _settle_balance(booking: Any) -> None:
    _settle_deposit(booking)
    booking.arm_balance()
    booking.record_balance()
    mark_payment_paid(booking, PaymentPurpose.BALANCE.value)


def _run(ctx: SeedContext) -> int:
    if ctx.dashboard_factor <= 0 or not ctx.properties or not ctx.terms:
        return 0
    factor = ctx.dashboard_factor
    terms = ctx.terms[0]
    expires_at = timezone.now() + timedelta(days=30)
    candidates = _candidates(ctx)
    made = 0
    showcase = 0

    def free_candidate(date_from: date, date_to: date, *, exclude: set[int]) -> Any:
        nonlocal showcase
        prop = next(
            (p for p in candidates if p.pk not in exclude and _is_free(p, date_from, date_to)),
            None,
        )
        if prop is None:
            prop = _new_showcase_property(ctx)
            # Reusable for later (disjoint) windows — without this, every
            # unsatisfiable window mints another villa.
            candidates.append(prop)
            showcase += 1
        return prop

    # Arrivals today (rest BALANCE_PAID) — one per villa; remember the hosts so
    # departures can reuse them for a realistic same-day changeover.
    hosts: list[Any] = []
    arrival_from, arrival_to = ctx.today, ctx.today + timedelta(days=_TODAY_NIGHTS)
    for _ in range(_ARRIVALS * factor):
        prop = free_candidate(arrival_from, arrival_to, exclude={p.pk for p in hosts})
        booking = _open_stay(ctx, prop, arrival_from, arrival_to, terms, expires_at)
        if booking is None:
            continue
        _settle_balance(booking)
        hosts.append(prop)
        made += 1

    # Departures today (rest BALANCE_PAID — see module docstring for why not
    # CHECKED_IN) — the half-open windows abut at today, so a reused host
    # renders an AM/PM changeover day where times are set.
    departure_from, departure_to = ctx.today - timedelta(days=_TODAY_NIGHTS), ctx.today
    for i in range(_DEPARTURES * factor):
        if i < len(hosts) and _is_free(hosts[i], departure_from, departure_to):
            prop = hosts[i]
        else:
            prop = free_candidate(departure_from, departure_to, exclude=set())
        booking = _open_stay(ctx, prop, departure_from, departure_to, terms, expires_at)
        if booking is None:
            continue
        _settle_balance(booking)
        made += 1

    # Awaiting balance — staggered future windows so one villa can host several.
    for i in range(_AWAITING_BALANCE * factor):
        start = ctx.today + timedelta(days=35 + 9 * i)
        end = start + timedelta(days=7)
        prop = free_candidate(start, end, exclude=set())
        booking = _open_stay(ctx, prop, start, end, terms, expires_at)
        if booking is None:
            continue
        _settle_deposit(booking)
        booking.arm_balance()
        made += 1

    # NEW enquiries — plain factory rows, no transition.
    pool = candidates or ctx.properties
    for _ in range(_NEW_ENQUIRIES * factor):
        enquiry = cast(
            Enquiry, EnquiryFactory(guest=pick_guest(ctx), property=ctx.rng.choice(pool))
        )
        ctx.enquiry_pks.append(enquiry.pk)
        made += 1

    made += _seed_owner_upcoming(ctx, terms, expires_at, factor)

    if showcase:
        logger.info("seed.dashboard_showcase_minted", count=showcase)
    return made


def _seed_owner_upcoming(ctx: SeedContext, terms: Any, expires_at: Any, factor: int) -> int:
    """DEPOSIT_PAID stays in the owner portal's 30-day window, on granted
    villas only — opportunistic (no showcase top-up: a minted villa would have
    no grant and wouldn't show on the owner dashboard anyway)."""
    from owners.models import OwnerOrgProperty

    granted = [
        g.property
        for g in OwnerOrgProperty.objects.filter(
            organisation__name=_ORG_NAME, end_date__isnull=True
        ).select_related("property")
        if g.property.status == "active" and not _requires_pre_approval(g.property)
    ]
    if not granted:
        return 0
    booked_pks = set(
        Booking.objects.filter(property__in=granted).values_list("property_id", flat=True)
    )
    granted.sort(key=lambda p: p.pk not in booked_pks)

    target = _UPCOMING * factor
    made = 0
    for offset in _UPCOMING_OFFSETS:
        for prop in granted:
            if made >= target:
                return made
            start = ctx.today + timedelta(days=offset)
            end = start + timedelta(days=_UPCOMING_NIGHTS)
            if not _is_free(prop, start, end):
                continue
            booking = _open_stay(ctx, prop, start, end, terms, expires_at)
            if booking is None:
                continue
            _settle_deposit(booking)
            made += 1
    return made


# `refunds` is a dependency because its goodwill cohort queries BALANCE_PAID
# bookings DB-wide — running after it keeps the curated arrivals-today
# bookings refund-free (a guest arriving today with a REJECTED/FAILED refund
# is incoherent demo data).
register(
    Stage(
        name="dashboard_activity",
        run=_run,
        depends_on=(
            "bookings",
            "availability_blocks",
            "owner_orgs",
            "property_lifecycle",
            "refunds",
        ),
    )
)
