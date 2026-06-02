"""Seed the property graph: Property + RatePlan/RateCard/RateRule + Discount +
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
    RateCardFactory,
    RatePlanFactory,
    RateRuleFactory,
)
from properties.enums import PrefilledChangeOverDay
from properties.factories import (
    ChangeOverRuleFactory,
    PropertyFactory,
    RegionFactory,
    villa_manifest,
)
from properties.models import Country
from seeding.context import SeedContext
from seeding.registry import Stage, register


def _parse_hhmm(value: str) -> time:
    """Parse an "HH:MM" changeover-time knob into a `time`."""
    return datetime.strptime(value, "%H:%M").time()


def _run(ctx: SeedContext) -> int:
    spread = ctx.knobs.booking_date_spread_days
    plan_kwargs: dict[str, Any] = {}
    rule_kwargs: dict[str, Any] = {}
    discount_kwargs: dict[str, Any] = {}
    if spread > 30:
        buffer = timedelta(days=spread + 60)
        plan_kwargs = {
            "effective_from": ctx.today - buffer,
            "effective_to": ctx.today + buffer,
        }
        rule_kwargs = {
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
    # property a real villa identity (name/location/description) coherent with
    # its imagery, exhausting every villa before any repeats. Empty without the
    # generated pool -> properties keep the legacy random shape.
    villa_pool: list[dict[str, Any]] = villa_manifest()

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
            extra_kwargs["display_name"] = villa["display_name"]
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
        if dirty_settings:
            prop.settings.save(update_fields=dirty_settings)
        plan = RatePlanFactory(property=prop, currency=currency, **plan_kwargs)
        card = RateCardFactory(plan=plan)
        RateRuleFactory(card=card, **rule_kwargs)
        DiscountFactory(property=prop, **discount_kwargs)
        ExtraFactory(property=prop, currency=currency)
        # Drop a permissive ChangeOverRule on every third property so the
        # model isn't permanently empty in dev. `ANY` is unconstrained at
        # quote time so the seeder's arbitrary stay starts are unaffected —
        # operators can tighten the day in the admin to see the validation
        # branch fire.
        if i % 3 == 0:
            ChangeOverRuleFactory(
                property=prop,
                day=PrefilledChangeOverDay.ANY,
            )
        ctx.properties.append(prop)
    return ctx.n_properties


register(Stage(name="properties", run=_run, depends_on=("system_setup", "groups")))
