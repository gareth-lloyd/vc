"""Seed the property graph: Property + RatePlan/RatePeriod/RateBand + Discount +
Extra, optionally rotated across multiple currencies and groups.

Currency / group rotation is opt-in via the v2 dials:

* If `ctx.currencies` has more than one entry, properties spread evenly
  across them so EUR/USD pricing shows up in the dev DB.
* If `ctx.groups` is non-empty, properties join one of those pre-seeded
  groups instead of getting a fresh one-per-property group.

Otherwise the legacy single-currency / per-property-group shape is
preserved (the `happy` profile still produces byte-for-byte equivalent
output to the pre-v2 seeder).
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, cast

from pricing.factories import (
    DiscountFactory,
    ExtraFactory,
    RateBandFactory,
    RatePeriodFactory,
    RatePlanFactory,
)
from properties.enums import PrefilledChangeOverDay
from properties.factories import (
    ChangeOverRuleFactory,
    PropertyFactory,
    RegionFactory,
    villa_manifest,
)
from properties.models import Country
from properties.services.changeover import ChangeoverService
from seeding._pricing_helpers import (
    _FLAT_BRACKETS,
    assign_commission,
    build_seasonal_periods,
    draw_base_nightly,
    party_brackets,
    seed_included_services,
)
from seeding.context import SeedContext
from seeding.registry import Stage, register


def _parse_hhmm(value: str) -> time:
    """Parse an "HH:MM" changeover-time knob into a `time`."""
    return datetime.strptime(value, "%H:%M").time()


def _changeover_day_plan(ctx: SeedContext) -> list[str]:
    """Pre-draw each villa's changeover day from the weighted knob.

    A deterministic floor of unconstrained ("any") villas — the knob's "any"
    weight as a guaranteed share, never below 2 — is reserved before the
    weighted draw fills the rest, mirroring the `_partition_tiers` floor
    pattern. Without it a small run can leave 0 unconstrained villas, and
    dashboard_activity (which needs villas that can host today-anchored short
    stays) would mint a showcase villa for every cohort, ballooning the
    portfolio. The hard minimum of 2 holds even when the knob's "any" weight
    is lowered to 0 — that guarantee is dashboard_activity's, not the
    distribution's.
    """
    weights = ctx.knobs.changeover_day_weights
    if not weights:
        return []
    n = ctx.n_properties
    any_weight = dict(weights).get(PrefilledChangeOverDay.ANY.value, 0.0)
    floor = min(n, max(2, round(any_weight * n)))
    days = [day for day, _ in weights]
    day_weights = [w for _, w in weights]
    plan = [PrefilledChangeOverDay.ANY.value] * floor + [
        ctx.rng.choices(days, weights=day_weights)[0] for _ in range(n - floor)
    ]
    ctx.rng.shuffle(plan)
    return plan


def _run(ctx: SeedContext) -> int:
    spread = ctx.knobs.booking_date_spread_days
    plan_kwargs: dict[str, Any] = {}
    period_kwargs: dict[str, Any] = {}
    discount_kwargs: dict[str, Any] = {}
    if spread > 30:
        buffer = timedelta(days=spread + 60)
        plan_kwargs = {
            "effective_from": ctx.today - buffer,
            "effective_to": ctx.today + buffer,
        }
        period_kwargs = {
            "date_from": ctx.today - buffer,
            "date_to": ctx.today + buffer,
        }
        discount_kwargs = {
            "valid_from": ctx.today - buffer,
            "valid_to": ctx.today + buffer,
        }

    currency_pool: list[Any] = list(ctx.currencies.values()) or [ctx.default_currency]
    group_pool: list[Any] = list(ctx.groups)
    # Villa entries with generated imagery. Cycling this list assigns each
    # property imagery plus a coherent location/description, exhausting every
    # villa before any repeats. Names are NOT taken from the manifest — the
    # factory's deterministic villa_name menu keeps them unique where the
    # 20-entry manifest would repeat. Empty without the generated pool ->
    # properties keep the legacy random shape.
    villa_pool: list[dict[str, Any]] = villa_manifest()
    day_plan = _changeover_day_plan(ctx)

    for i in range(ctx.n_properties):
        currency = currency_pool[i % len(currency_pool)]
        extra_kwargs: dict[str, Any] = {}
        if group_pool:
            extra_kwargs["group"] = group_pool[i % len(group_pool)]
        villa = villa_pool[i % len(villa_pool)] if villa_pool else None
        if villa is not None:
            # Reuse the migration-seeded Country row and name the Region after
            # the villa's location so the property reads coherently with its
            # imagery. `.get` (not get_or_create) so a manifest country_iso2
            # absent from the ISO-3166 seed fails loudly instead of creating a
            # malformed Country row.
            country = Country.objects.get(iso2=villa["country_iso2"])
            locality = villa["location_tag"].rsplit(",", 1)[0].strip()
            extra_kwargs["region"] = RegionFactory(country=country, name=locality)
            extra_kwargs["children__villa"] = villa
        # Pre-approval is meaningless without an owner to approve, so a
        # property flagged for pre-approval must also get a primary owner
        # contact — otherwise the owner-approval email handler skips and
        # the dev DB ends up with PENDING_OWNER_APPROVAL bookings that
        # nobody can act on.
        wants_pre_approval = ctx.rng.random() < ctx.knobs.pct_pre_approval_property
        wants_owner = wants_pre_approval or ctx.rng.random() < ctx.knobs.pct_owner_contact
        prop = cast(
            Any,
            PropertyFactory(
                with_owner_contact=wants_owner,
                **extra_kwargs,
            ),
        )
        if villa is not None:
            ctx.property_villa[prop.pk] = villa["slug"]
        # Collect every dirtied PropertySettings field so a pre-approval villa
        # with changeover times writes once, not twice.
        dirty_settings: list[str] = []
        if wants_pre_approval:
            prop.settings.bookings_require_pre_approval = True
            dirty_settings.append("bookings_require_pre_approval")
        # Clock times let back-to-back stays render an AM/PM changeover day on
        # the availability calendar. Off (None, None) for happy, which keeps
        # the times null and the changeover split suppressed.
        check_out, check_in = ctx.knobs.changeover_times
        if check_out is not None and check_in is not None:
            prop.settings.check_out_time = _parse_hhmm(check_out)
            prop.settings.check_in_time = _parse_hhmm(check_in)
            dirty_settings += ["check_out_time", "check_in_time"]
        # Mirror the legacy prod shape: most villas carry a specific
        # changeover day plus a whole-week minimum stay, on both the
        # legacy-semantics settings fields and the engine-enforced
        # RatePeriod.min_nights (written below at period creation).
        assigned_day = day_plan[i] if day_plan else PrefilledChangeOverDay.ANY.value
        constrained = assigned_day != PrefilledChangeOverDay.ANY.value
        if constrained:
            prop.settings.changeover_day = assigned_day
            prop.settings.min_nights_rental = ctx.knobs.constrained_min_nights
            dirty_settings += ["changeover_day", "min_nights_rental"]
        if dirty_settings:
            prop.settings.save(update_fields=dirty_settings)
        min_nights = ctx.knobs.constrained_min_nights if constrained else 1
        plan = RatePlanFactory(property=prop, currency=currency, **plan_kwargs)
        seed_included_services(prop, i)
        if ctx.knobs.realistic_pricing:
            brackets = _FLAT_BRACKETS
            if ctx.rng.random() < ctx.knobs.pct_occupancy_bands:
                # The factory hardcodes guests=8, which would collapse the
                # natural 1-8 / 9-12 / 13+ brackets to a single band — bump
                # capacity so the bands are real.
                capacity = prop.capacity
                capacity.guests = ctx.rng.randint(10, 16)
                capacity.save(update_fields=["guests"])
                brackets = party_brackets(capacity.guests)
            build_seasonal_periods(
                plan,
                draw_base_nightly(ctx.rng, currency.code),
                min_nights=min_nights,
                brackets=brackets,
                wide_spread=ctx.rng.random() < 0.08,
            )
            assign_commission(ctx.rng, prop)
            if ctx.rng.random() < ctx.knobs.pct_second_currency and len(currency_pool) > 1:
                # Legacy: ~13% of villas price in 2+ currencies (by design —
                # the quote builder handles a mixed-currency list). Dated one
                # day earlier than the primary plan so `pick_preferred_plan`
                # (most recent effective_from wins) keeps currency-less
                # quotes — and therefore the booking stages — on the primary.
                alt = currency_pool[(i + 1) % len(currency_pool)]
                alt_plan = RatePlanFactory(
                    property=prop,
                    currency=alt,
                    effective_from=plan.effective_from - timedelta(days=1),
                    effective_to=plan.effective_to,
                )
                build_seasonal_periods(
                    alt_plan,
                    draw_base_nightly(ctx.rng, alt.code),
                    min_nights=min_nights,
                    brackets=brackets,
                )
        else:
            period = RatePeriodFactory(plan=plan, min_nights=min_nights, **period_kwargs)
            RateBandFactory(period=period)
        # Legacy discounts are effectively dead — gate behind the knob. The
        # >= 1.0 short-circuit keeps happy off the rng (byte-for-byte output).
        if ctx.knobs.pct_discount >= 1.0 or ctx.rng.random() < ctx.knobs.pct_discount:
            DiscountFactory(property=prop, **discount_kwargs)
        ExtraFactory(property=prop, currency=currency)
        # Drop a ChangeOverRule on every third property so the model isn't
        # permanently empty in dev. The rule's day MUST match the villa's
        # assigned day: a rule window beats PropertySettings.changeover_day in
        # ChangeoverService.effective_day, so an `ANY` rule on a Saturday
        # villa would silently un-constrain it for the window.
        if i % 3 == 0:
            ChangeOverRuleFactory(property=prop, day=assigned_day)
        if day_plan:
            # Recorded via the real resolver (not the assignment) so the map
            # can never drift from what the engine will actually enforce.
            ctx.property_stay_rules[prop.pk] = (
                ChangeoverService.required_weekday(prop, ctx.today),
                ctx.knobs.constrained_min_nights if constrained else 1,
            )
        ctx.properties.append(prop)
    return ctx.n_properties


register(Stage(name="properties", run=_run, depends_on=("system_setup", "groups")))
